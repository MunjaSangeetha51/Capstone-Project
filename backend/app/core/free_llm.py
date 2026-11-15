"""FreeOpenRouterClient — 100% free, zero-cost LLM client with failover, caching, and structured output."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

T = TypeVar("T", bound=BaseModel)

# ──────────────────────────────────────────────────────────────────────────────
# FREE MODEL POOLS (must end with :free or be "openrouter/free")
# ──────────────────────────────────────────────────────────────────────────────
FREE_REASONING_MODELS: list[str] = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "cohere/north-mini-code:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "openrouter/free",
]

FREE_FAST_MODELS: list[str] = [
    "nvidia/nemotron-3.5-lightning:free",
    "google/gemma-4-31b-it:free",
    "liquid/lfm-3-1.7b:free",
    "openrouter/free",
]

ALL_FREE_MODELS = FREE_REASONING_MODELS + FREE_FAST_MODELS


# ──────────────────────────────────────────────────────────────────────────────
# Validation guard: NEVER allow a paid model
# ──────────────────────────────────────────────────────────────────────────────
def _validate_free_model(model: str) -> None:
    """Raise ValueError if model is not in the free allow-list."""
    if model not in ALL_FREE_MODELS:
        raise ValueError(
            f"Model '{model}' is not in the FREE allow-list. "
            f"Allowed: {ALL_FREE_MODELS}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# SQLite Response Cache (keyed by sha256(system_prompt + prompt + schema_name))
# ──────────────────────────────────────────────────────────────────────────────
class LLMCache:
    """Thread-safe SQLite cache for LLM responses."""

    def __init__(self, db_path: str | Path = "llm_cache.db") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_cache (
                    key       TEXT PRIMARY KEY,
                    response  TEXT NOT NULL,
                    model     TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_created_at ON llm_cache(created_at)"
            )
            conn.commit()

    def _make_key(self, system_prompt: str, prompt: str, schema_name: str) -> str:
        content = f"{system_prompt}|{prompt}|{schema_name}"
        return hashlib.sha256(content.encode()).hexdigest()

    def get(self, system_prompt: str, prompt: str, schema_name: str) -> str | None:
        key = self._make_key(system_prompt, prompt, schema_name)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT response FROM llm_cache WHERE key = ?", (key,)
            ).fetchone()
        return row[0] if row else None

    def set(
        self, system_prompt: str, prompt: str, schema_name: str, response: str, model: str
    ) -> None:
        key = self._make_key(system_prompt, prompt, schema_name)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO llm_cache (key, response, model, created_at) VALUES (?, ?, ?, ?)",
                (key, response, model, int(time.time())),
            )
            conn.commit()

    def stats(self) -> dict[str, int]:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0]
        return {"total_entries": total}


# ──────────────────────────────────────────────────────────────────────────────
# JSON repair helper for smaller free models
# ──────────────────────────────────────────────────────────────────────────────
_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*(\{.*?\})\s*```$", re.DOTALL | re.MULTILINE)


def _repair_json(raw: str) -> str:
    """Strip markdown code fences and try to extract a valid JSON object."""
    # Try to extract from ```json ... ``` fences
    match = _JSON_FENCE_RE.search(raw)
    if match:
        return match.group(1).strip()
    # Fallback: find first { and last }
    first = raw.find("{")
    last = raw.rfind("}")
    if first != -1 and last != -1 and last > first:
        return raw[first : last + 1]
    return raw.strip()


# ──────────────────────────────────────────────────────────────────────────────
# FreeOpenRouterClient
# ──────────────────────────────────────────────────────────────────────────────
class FreeOpenRouterClient:
    """
    Async OpenRouter client that guarantees $0.00 token spend.

    Features:
    - Strict free-model allow-list guard
    - Multi-model failover via OpenRouter's native `extra_body={"models": [...], "route": "fallback"}`
    - Pydantic v2 structured output with JSON repair
    - SQLite response cache to respect 20 RPM free tier limit
    - Automatic retry with exponential backoff on 429/503
    """

    BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)

    def __init__(
        self,
        api_key: str | None = None,
        *,
        cache: LLMCache | None = None,
        default_tier: str = "fast",
    ) -> None:
        """
        Args:
            api_key: OpenRouter API key (optional - works without for free models)
            cache: Optional LLMCache instance (creates default if not provided)
            default_tier: "fast" or "reasoning" — selects model pool
        """
        self._api_key = api_key
        self._cache = cache or LLMCache()
        self._default_tier = default_tier
        self._client: httpx.AsyncClient | None = None
        self._model_pool_map = {
            "fast": FREE_FAST_MODELS,
            "reasoning": FREE_REASONING_MODELS,
        }
        self._stats = {
            "requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
            "last_model_used": None,
        }

    async def __aenter__(self) -> FreeOpenRouterClient:
        await self._ensure_client()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def _ensure_client(self) -> None:
        if self._client is None or self._client.is_closed:
            headers = {
                "Content-Type": "application/json",
                "HTTP-Referer": "https://skillproof.app",
                "X-Title": "SkillProof",
            }
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers=headers,
                timeout=self.DEFAULT_TIMEOUT,
            )

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _get_model_pool(self, tier: str) -> list[str]:
        pool = self._model_pool_map.get(tier.lower())
        if not pool:
            raise ValueError(f"Unknown tier '{tier}'. Use 'fast' or 'reasoning'.")
        # Validate every model in pool at runtime
        for m in pool:
            _validate_free_model(m)
        return pool

    def _build_system_prompt(
        self, system_prompt: str, pydantic_model: type[T]
    ) -> str:
        """Inject JSON schema into system prompt for structured output."""
        schema = pydantic_model.model_json_schema()
        schema_json = json.dumps(schema, separators=(",", ":"))
        return (
            f"{system_prompt}\n\n"
            f"You MUST respond with ONLY a valid JSON object matching this exact schema:\n"
            f"{schema_json}\n\n"
            f"No extra text, no markdown, no commentary. Just the JSON object."
        )

    async def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        pydantic_model: type[T],
        *,
        tier: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> T:
        """
        Generate structured output using free models with automatic failover.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            pydantic_model: Pydantic v2 model for validation
            tier: "fast" or "reasoning" (default from client config)
            temperature: Sampling temperature
            max_tokens: Max tokens in response

        Returns:
            Validated Pydantic model instance

        Raises:
            ValueError: If all free models fail or response invalid
        """
        await self._ensure_client()
        assert self._client is not None

        tier = tier or self._default_tier
        model_pool = self._get_model_pool(tier)
        schema_name = pydantic_model.__name__

        # Check cache first
        cached = self._cache.get(system_prompt, prompt, schema_name)
        if cached is not None:
            self._stats["cache_hits"] += 1
            try:
                return pydantic_model.model_validate_json(cached)
            except Exception:
                # Cache corrupted, fall through to fresh request
                pass

        self._stats["cache_misses"] += 1
        self._stats["requests"] += 1

        # Build request with OpenRouter native failover
        system_prompt_enhanced = self._build_system_prompt(system_prompt, pydantic_model)
        payload = {
            "model": model_pool[0],  # Primary model
            "messages": [
                {"role": "system", "content": system_prompt_enhanced},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "extra_body": {
                "models": model_pool,  # OpenRouter will auto-failover on 429/503
                "route": "fallback",
            },
        }

        # Retry logic for transient errors
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
            wait=wait_exponential_jitter(initial=1, max=10),
            stop=stop_after_attempt(3),
            reraise=True,
        ):
            with attempt:
                resp = await self._client.post("/chat/completions", json=payload)
                resp.raise_for_status()

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        model_used = data.get("model", model_pool[0])

        # Repair and validate JSON
        repaired = _repair_json(content)
        try:
            validated = pydantic_model.model_validate_json(repaired)
        except Exception as e:
            self._stats["errors"] += 1
            raise ValueError(f"Failed to validate response as {schema_name}: {e}") from e

        # Cache successful response
        self._cache.set(system_prompt, prompt, schema_name, repaired, model_used)
        self._stats["last_model_used"] = model_used

        return validated

    def get_stats(self) -> dict[str, Any]:
        """Return client statistics including cache hit rate."""
        cache_stats = self._cache.stats()
        total_reqs = self._stats["cache_hits"] + self._stats["cache_misses"]
        hit_rate = (
            round(100 * self._stats["cache_hits"] / total_reqs, 1) if total_reqs else 0.0
        )
        return {
            **self._stats,
            **cache_stats,
            "cache_hit_rate_pct": hit_rate,
            "default_tier": self._default_tier,
            "available_models": ALL_FREE_MODELS,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Convenience singleton for app lifespan
# ──────────────────────────────────────────────────────────────────────────────
_default_client: FreeOpenRouterClient | None = None


async def get_free_llm_client() -> FreeOpenRouterClient:
    """Get or create the default FreeOpenRouterClient singleton."""
    global _default_client
    if _default_client is None:
        _default_client = FreeOpenRouterClient()
        await _default_client.__aenter__()
    return _default_client


async def close_free_llm_client() -> None:
    """Close the default client (call on app shutdown)."""
    global _default_client
    if _default_client is not None:
        await _default_client.aclose()
        _default_client = None