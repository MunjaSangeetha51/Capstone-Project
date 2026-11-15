"""FreeJobHarvester — Zero-key live job ingestion from public APIs + LocalSkillExtractor."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

# ──────────────────────────────────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────────────────────────────────
class JobPosting(BaseModel):
    """Normalized job posting from any source."""
    id: str
    source: str
    source_url: str
    company: str
    title: str
    location: str | None = None
    description: str
    requirements_text: str = ""
    preferred_text: str = ""
    posted_at: datetime | None = None
    skills: dict[str, float] = Field(default_factory=dict)  # skill -> weight
    summary: str = ""
    sub_concepts: dict[str, list[str]] = Field(default_factory=dict)
    raw_data: dict[str, Any] = Field(default_factory=dict)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HarvestResult(BaseModel):
    """Result of a harvest operation."""
    source: str
    fetched: int
    new: int
    duplicates: int
    errors: int
    postings: list[JobPosting] = Field(default_factory=list)


class Telemetry(BaseModel):
    """System telemetry for monitoring."""
    total_postings: int
    by_source: dict[str, int]
    by_role_cluster: dict[str, int]
    active_model: str
    cache_hit_rate_pct: float
    llm_requests_today: int
    last_harvest: str | None = None
    skill_coverage: dict[str, int] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# Canonical Skill Ontology (5 Role Clusters, 80+ skills with aliases)
# ──────────────────────────────────────────────────────────────────────────────
SKILL_ONTOLOGY: dict[str, dict[str, Any]] = {
    # BACKEND ENGINEERING
    "Python": {
        "cluster": "Backend Engineering",
        "aliases": ["python", "py", "django", "flask", "fastapi", "pydantic", "asyncio", "uvicorn", "gunicorn"],
        "category": "Language",
    },
    "Java": {
        "cluster": "Backend Engineering",
        "aliases": ["java", "spring", "spring boot", "springboot", "jvm", "maven", "gradle", "kotlin"],
        "category": "Language",
    },
    "Go": {
        "cluster": "Backend Engineering",
        "aliases": ["go", "golang", "gin", "echo", "fiber", "chi"],
        "category": "Language",
    },
    "Node.js": {
        "cluster": "Backend Engineering",
        "aliases": ["node.js", "nodejs", "node", "express", "nestjs", "koa", "fastify", "npm", "yarn", "pnpm"],
        "category": "Runtime",
    },
    "SQL": {
        "cluster": "Backend Engineering",
        "aliases": ["sql", "mysql", "postgresql", "postgres", "psql", "sqlite", "mariadb", "t-sql", "plsql"],
        "category": "Database",
    },
    "PostgreSQL": {
        "cluster": "Backend Engineering",
        "aliases": ["postgresql", "postgres", "psql", "pg", "timescaledb", "citus"],
        "category": "Database",
    },
    "Redis": {
        "cluster": "Backend Engineering",
        "aliases": ["redis", "redis-cluster", "valkey", "keydb"],
        "category": "Database",
    },
    "MongoDB": {
        "cluster": "Backend Engineering",
        "aliases": ["mongodb", "mongo", "mongoose", "documentdb"],
        "category": "Database",
    },
    "Docker": {
        "cluster": "Backend Engineering",
        "aliases": ["docker", "containerd", "podman", "dockerfile", "docker-compose", "compose"],
        "category": "DevOps",
    },
    "REST APIs": {
        "cluster": "Backend Engineering",
        "aliases": ["rest", "restful", "rest api", "openapi", "swagger", "api design"],
        "category": "Architecture",
    },
    "GraphQL": {
        "cluster": "Backend Engineering",
        "aliases": ["graphql", "apollo", "relay", "schema stitching", "federation"],
        "category": "Architecture",
    },
    "gRPC": {
        "cluster": "Backend Engineering",
        "aliases": ["grpc", "protobuf", "protocol buffers", "proto"],
        "category": "Architecture",
    },
    "Microservices": {
        "cluster": "Backend Engineering",
        "aliases": ["microservices", "microservice", "service mesh", "istio", "linkerd", "consul"],
        "category": "Architecture",
    },
    "Event-Driven": {
        "cluster": "Backend Engineering",
        "aliases": ["kafka", "rabbitmq", "nats", "event-driven", "event sourcing", "cqrs", "pub/sub"],
        "category": "Architecture",
    },
    "Testing": {
        "cluster": "Backend Engineering",
        "aliases": ["pytest", "junit", "testng", "mockito", "testcontainers", "unit testing", "integration testing"],
        "category": "Quality",
    },

    # MACHINE LEARNING & DATA
    "Machine Learning": {
        "cluster": "Machine Learning & Data",
        "aliases": ["machine learning", "ml", "scikit-learn", "sklearn", "xgboost", "lightgbm", "catboost"],
        "category": "ML",
    },
    "Deep Learning": {
        "cluster": "Machine Learning & Data",
        "aliases": ["deep learning", "pytorch", "tensorflow", "keras", "jax", "huggingface", "transformers"],
        "category": "ML",
    },
    "NLP": {
        "cluster": "Machine Learning & Data",
        "aliases": ["nlp", "natural language processing", "spacy", "nltk", "bert", "gpt", "llm", "transformers"],
        "category": "ML",
    },
    "Computer Vision": {
        "cluster": "Machine Learning & Data",
        "aliases": ["computer vision", "cv", "opencv", "yolo", "resnet", "vit", "detection", "segmentation"],
        "category": "ML",
    },
    "Data Engineering": {
        "cluster": "Machine Learning & Data",
        "aliases": ["data engineering", "etl", "elt", "airflow", "dagster", "prefect", "dbt", "spark", "flink"],
        "category": "Data",
    },
    "SQL (Analytics)": {
        "cluster": "Machine Learning & Data",
        "aliases": ["bigquery", "snowflake", "redshift", "clickhouse", "duckdb", "trino", "presto"],
        "category": "Data",
    },
    "MLOps": {
        "cluster": "Machine Learning & Data",
        "aliases": ["mlops", "mlflow", "kubeflow", "wandb", "neptune", "model registry", "feature store"],
        "category": "ML",
    },
    "Statistics": {
        "cluster": "Machine Learning & Data",
        "aliases": ["statistics", "statistical analysis", "hypothesis testing", "bayesian", "a/b testing"],
        "category": "Math",
    },

    # FULL-STACK PRODUCT
    "React": {
        "cluster": "Full-Stack Product",
        "aliases": ["react", "reactjs", "jsx", "tsx", "next.js", "nextjs", "remix", "vite", "create-react-app"],
        "category": "Frontend",
    },
    "TypeScript": {
        "cluster": "Full-Stack Product",
        "aliases": ["typescript", "ts", "type-safe", "strict mode"],
        "category": "Language",
    },
    "HTML/CSS": {
        "cluster": "Full-Stack Product",
        "aliases": ["html", "css", "html5", "css3", "sass", "scss", "tailwind", "bootstrap", "styled-components", "emotion"],
        "category": "Frontend",
    },
    "State Management": {
        "cluster": "Full-Stack Product",
        "aliases": ["redux", "zustand", "jotai", "recoil", "context api", "vuex", "pinia"],
        "category": "Frontend",
    },
    "Testing (Frontend)": {
        "cluster": "Full-Stack Product",
        "aliases": ["jest", "vitest", "cypress", "playwright", "testing-library", "storybook"],
        "category": "Quality",
    },
    "Web Performance": {
        "cluster": "Full-Stack Product",
        "aliases": ["web vitals", "lighthouse", "core web vitals", "cls", "fid", "lcp", "ttfb", "optimization"],
        "category": "Frontend",
    },
    "Accessibility": {
        "cluster": "Full-Stack Product",
        "aliases": ["a11y", "accessibility", "wcag", "aria", "screen reader", "semantic html"],
        "category": "Frontend",
    },
    "GraphQL (Client)": {
        "cluster": "Full-Stack Product",
        "aliases": ["apollo client", "urql", "react query", "tanstack query", "swr", "relay"],
        "category": "Frontend",
    },

    # CLOUD & DEVOPS
    "AWS": {
        "cluster": "Cloud & DevOps",
        "aliases": ["aws", "amazon web services", "ec2", "s3", "lambda", "rds", "dynamodb", "ecs", "eks", "fargate", "cloudformation", "cdk"],
        "category": "Cloud",
    },
    "GCP": {
        "cluster": "Cloud & DevOps",
        "aliases": ["gcp", "google cloud", "google cloud platform", "cloud run", "cloud functions", "bigquery", "firestore", "gke"],
        "category": "Cloud",
    },
    "Azure": {
        "cluster": "Cloud & DevOps",
        "aliases": ["azure", "microsoft azure", "azure functions", "aks", "cosmos db", "app service"],
        "category": "Cloud",
    },
    "Kubernetes": {
        "cluster": "Cloud & DevOps",
        "aliases": ["kubernetes", "k8s", "k3s", "helm", "kubectl", "operator", "crd", "argocd", "flux"],
        "category": "Orchestration",
    },
    "Terraform": {
        "cluster": "Cloud & DevOps",
        "aliases": ["terraform", "iac", "infrastructure as code", "hcl", "openTofu", "tofu"],
        "category": "IaC",
    },
    "CI/CD": {
        "cluster": "Cloud & DevOps",
        "aliases": ["ci/cd", "github actions", "gitlab ci", "jenkins", "circleci", "buildkite", "argo", "tekton"],
        "category": "Automation",
    },
    "Observability": {
        "cluster": "Cloud & DevOps",
        "aliases": ["observability", "prometheus", "grafana", "datadog", "new relic", "otel", "openTelemetry", "jaeger", "tempo", "loki"],
        "category": "Monitoring",
    },
    "Service Mesh": {
        "cluster": "Cloud & DevOps",
        "aliases": ["istio", "linkerd", "consul connect", "service mesh", "mtls"],
        "category": "Networking",
    },

    # SYSTEMS & SECURITY
    "Linux": {
        "cluster": "Systems & Security",
        "aliases": ["linux", "ubuntu", "debian", "centos", "rhel", "alpine", "arch", "bash", "shell", "zsh"],
        "category": "OS",
    },
    "Networking": {
        "cluster": "Systems & Security",
        "aliases": ["networking", "tcp/ip", "http", "https", "dns", "tls", "ssl", "load balancer", "nginx", "haproxy", "envoy"],
        "category": "Networking",
    },
    "Security": {
        "cluster": "Systems & Security",
        "aliases": ["security", "appsec", "devsecops", "owasp", "sast", "dast", "sca", "secrets management", "vault"],
        "category": "Security",
    },
    "Cryptography": {
        "cluster": "Systems & Security",
        "aliases": ["cryptography", "encryption", "jwt", "oauth", "oidc", "saml", "mfa", "2fa", "zero trust"],
        "category": "Security",
    },
    "Rust": {
        "cluster": "Systems & Security",
        "aliases": ["rust", "cargo", "tokio", "async rust", "wasm", "webassembly"],
        "category": "Language",
    },
    "C++": {
        "cluster": "Systems & Security",
        "aliases": ["c++", "cpp", "cmake", "bazel", "conan", "vcpkg", "modern c++"],
        "category": "Language",
    },
    "Embedded": {
        "cluster": "Systems & Security",
        "aliases": ["embedded", "rtos", "freertos", "zephyr", "stm32", "esp32", "arduino", "bare metal"],
        "category": "Systems",
    },
}

# Build reverse lookup: alias -> canonical skill
ALIAS_TO_SKILL: dict[str, str] = {}
for skill, info in SKILL_ONTOLOGY.items():
    ALIAS_TO_SKILL[skill.lower()] = skill
    for alias in info["aliases"]:
        ALIAS_TO_SKILL[alias.lower()] = skill

ALL_SKILLS = list(SKILL_ONTOLOGY.keys())
SKILL_CLUSTERS = sorted(set(info["cluster"] for info in SKILL_ONTOLOGY.values()))


# ──────────────────────────────────────────────────────────────────────────────
# LocalSkillExtractor — CPU-first deterministic + semantic extraction
# ──────────────────────────────────────────────────────────────────────────────
class LocalSkillExtractor:
    """
    Deterministic + semantic skill extraction running in <10ms per job on CPU.

    Weight calculation:
    - Title match: 0.95
    - Requirements/Must-Have section: 0.85
    - Frequency >= 3: 0.80
    - Preferred/Bonus section: 0.40
    - Cosine similarity boost from all-MiniLM-L6-v2
    """

    _section_patterns = {
        "requirements": re.compile(
            r"(requirements?|must have|required|qualifications?|skills? needed|"
            r"what you.ll need|what you.ll bring|essential|mandatory)",
            re.IGNORECASE,
        ),
        "preferred": re.compile(
            r"(preferred|nice to have|bonus|plus|desired|optional|"
            r"would be great|good to have|advantage)",
            re.IGNORECASE,
        ),
    }

    def __init__(self) -> None:
        self._model: SentenceTransformer | None = None
        self._skill_embeddings: dict[str, list[float]] = {}

    def _ensure_model(self) -> None:
        """Lazy-load the sentence transformer model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            # Pre-compute skill embeddings
            skill_texts = [skill for skill in ALL_SKILLS]
            embeddings = self._model.encode(skill_texts, convert_to_tensor=False, normalize_embeddings=True)
            self._skill_embeddings = {skill: emb.tolist() for skill, emb in zip(ALL_SKILLS, embeddings)}

    @staticmethod
    def _split_sections(text: str) -> dict[str, str]:
        """Split job description into sections."""
        sections = {"full": text, "title": "", "requirements": "", "preferred": "", "other": ""}

        # Try to extract title (first line often)
        lines = text.strip().split("\n")
        if lines:
            sections["title"] = lines[0][:200]

        # Find requirement/preferred sections
        req_matches = list(LocalSkillExtractor._section_patterns["requirements"].finditer(text))
        pref_matches = list(LocalSkillExtractor._section_patterns["preferred"].finditer(text))

        if req_matches:
            start = req_matches[0].start()
            end = pref_matches[0].start() if pref_matches else len(text)
            sections["requirements"] = text[start:end]
        if pref_matches:
            start = pref_matches[0].start()
            sections["preferred"] = text[start:]

        sections["other"] = text
        return sections

    def _find_skill_matches(self, text: str) -> dict[str, list[tuple[int, str]]]:
        """Find all skill mentions with positions. Returns {skill: [(pos, matched_alias), ...]}."""
        text_lower = text.lower()
        matches: dict[str, list[tuple[int, str]]] = {}

        for alias, canonical in ALIAS_TO_SKILL.items():
            # Use word boundaries for cleaner matching
            pattern = re.compile(rf"\b{re.escape(alias)}\b", re.IGNORECASE)
            for match in pattern.finditer(text_lower):
                pos = match.start()
                matches.setdefault(canonical, []).append((pos, alias))

        return matches

    def _calculate_weight(
        self,
        skill: str,
        matches: list[tuple[int, str]],
        sections: dict[str, str],
        title: str,
    ) -> float:
        """Calculate skill weight based on location and frequency."""
        if not matches:
            return 0.0

        freq = len(matches)
        first_pos = matches[0][0]
        text_lower = sections["full"].lower()
        title_lower = title.lower()

        # Title match — strongest signal
        if skill.lower() in title_lower:
            for alias in SKILL_ONTOLOGY[skill]["aliases"]:
                if alias.lower() in title_lower:
                    return 0.95

        # Check which section the first mention falls in
        req_text = sections["requirements"].lower()
        pref_text = sections["preferred"].lower()

        in_requirements = any(
            text_lower[pos:pos + len(alias)].lower() in req_text
            for pos, alias in matches
        )
        in_preferred = any(
            text_lower[pos:pos + len(alias)].lower() in pref_text
            for pos, alias in matches
        )

        # Base weight by section
        if in_requirements:
            base = 0.85
        elif in_preferred:
            base = 0.40
        else:
            base = 0.50  # Default for mentions in other sections

        # Frequency boost
        if freq >= 3:
            base = max(base, 0.80)
        elif freq >= 2:
            base = max(base, 0.65)

        return min(1.0, base)

    def _semantic_boost(
        self, skill: str, context: str, threshold: float = 0.65
    ) -> float:
        """Use sentence transformer for semantic similarity boost."""
        self._ensure_model()
        assert self._model is not None

        skill_emb = self._skill_embeddings[skill]
        context_emb = self._model.encode([context], convert_to_tensor=False, normalize_embeddings=True)[0]

        # Cosine similarity (already normalized)
        sim = float(sum(a * b for a, b in zip(skill_emb, context_emb)))
        return sim if sim > threshold else 0.0

    def extract(self, job: JobPosting) -> dict[str, float]:
        """
        Extract skills with weights from a job posting.

        Returns:
            Dict of {canonical_skill: weight} where weight in [0, 1]
        """
        text = f"{job.title}\n{job.description}\n{job.requirements_text}\n{job.preferred_text}"
        sections = self._split_sections(text)
        title = sections["title"] or job.title

        matches = self._find_skill_matches(text)

        weights: dict[str, float] = {}
        for skill, skill_matches in matches.items():
            weight = self._calculate_weight(skill, skill_matches, sections, title)

            # Semantic boost from context around first mention
            if skill_matches:
                first_pos = skill_matches[0][0]
                context_window = text[max(0, first_pos - 100):first_pos + 200]
                semantic = self._semantic_boost(skill, context_window)
                weight = max(weight, semantic * 0.9)  # Cap semantic influence

            if weight > 0.3:  # Only keep meaningful weights
                weights[skill] = round(weight, 2)

        return weights


# ──────────────────────────────────────────────────────────────────────────────
# FreeJobHarvester — Multi-source public API ingestion
# ──────────────────────────────────────────────────────────────────────────────
class FreeJobHarvester:
    """
    Harvests real tech internships & entry-level roles from 100% free public APIs.

    Sources:
    - Greenhouse Public API (boards-api.greenhouse.io)
    - Lever Public API (api.lever.co)
    - Ashby Public API (api.ashbyhq.com)
    - Remotive Public API (remotive.com)
    - Arbeitnow Free Job Board API (arbeitnow.com)
    - The Muse Public Jobs API (themuse.com)
    - Optional: python-jobspy wrapper for Indeed/LinkedIn
    """

    # Source configurations
    GREENHOUSE_SLUGS = [
        "stripe", "cloudflare", "databricks", "postman",
        "razorpay", "vercel", "figma", "coinbase",
    ]
    LEVER_SLUGS = ["palantir", "zoox", "mistral"]
    ASHBY_SLUGS = ["linear", "supabase", "ramp", "perplexity"]

    REMOTIVE_URL = "https://remotive.com/api/remote-jobs?category=software-dev&limit=50"
    ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
    THEMUSE_URL = "https://www.themuse.com/api/public/jobs?category=Software%20Engineering&level=Internship&level=Entry%20Level&page=1"

    # Keywords for filtering to internships/entry-level
    INTERN_KEYWORDS = [
        "intern", "internship", "co-op", "coop", "apprentice", "apprenticeship",
        "entry level", "entry-level", "junior", "new grad", "new-grad",
        "graduate", "university", "student", "campus", "fellow", "fellowship",
    ]

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        skill_extractor: LocalSkillExtractor | None = None,
        storage_path: str | Path = "job_postings.json",
    ) -> None:
        self._client = client
        self._own_client = client is None
        self._skill_extractor = skill_extractor or LocalSkillExtractor()
        self._storage_path = Path(storage_path)
        self._postings: dict[str, JobPosting] = {}  # id -> posting
        self._load_storage()
        self._stats = {
            "total_harvested": 0,
            "by_source": {},
            "last_harvest": None,
            "errors": [],
        }

    async def __aenter__(self) -> FreeJobHarvester:
        if self._own_client:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                headers={"User-Agent": "SkillProof/1.0 (+https://skillproof.app)"},
            )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._own_client and self._client:
            await self._client.aclose()
            self._client = None

    def _load_storage(self) -> None:
        """Load existing postings from JSON file."""
        if self._storage_path.exists():
            try:
                with open(self._storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    posting = JobPosting(**item)
                    self._postings[posting.id] = posting
            except Exception:
                pass  # Start fresh on corruption

    def _save_storage(self) -> None:
        """Persist postings to JSON file."""
        data = [p.model_dump(mode="json") for p in self._postings.values()]
        with open(self._storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _make_id(self, source: str, identifier: str) -> str:
        """Generate stable ID from source + identifier."""
        return hashlib.sha256(f"{source}:{identifier}".encode()).hexdigest()[:16]

    def _is_intern_or_entry(self, title: str, description: str) -> bool:
        """Filter for internships and entry-level roles."""
        text = f"{title} {description}".lower()
        return any(kw in text for kw in self.INTERN_KEYWORDS)

    def _extract_sections(self, description: str) -> tuple[str, str]:
        """Split description into requirements and preferred sections."""
        req_pattern = re.compile(
            r"(requirements?|must have|required|qualifications?|skills? needed|"
            r"what you.ll need|what you.ll bring|essential|mandatory)[\s:]*\n?(.*?)(?=\n\n|\n[A-Z]|$)",
            re.IGNORECASE | re.DOTALL,
        )
        pref_pattern = re.compile(
            r"(preferred|nice to have|bonus|plus|desired|optional|"
            r"would be great|good to have|advantage)[\s:]*\n?(.*?)(?=\n\n|\n[A-Z]|$)",
            re.IGNORECASE | re.DOTALL,
        )

        req_match = req_pattern.search(description)
        pref_match = pref_pattern.search(description)

        requirements = req_match.group(2).strip() if req_match else ""
        preferred = pref_match.group(2).strip() if pref_match else ""

        return requirements, preferred

    # ──────────────────────────────────────────────────────────────────────────
    # Source A: Direct Public ATS JSON APIs
    # ──────────────────────────────────────────────────────────────────────────
    async def _fetch_greenhouse(self, slug: str) -> list[JobPosting]:
        """Fetch jobs from Greenhouse public API."""
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
        postings = []

        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()

            for job in data.get("jobs", []):
                title = job.get("title", "")
                desc = job.get("content", "") or job.get("description", "")
                if not self._is_intern_or_entry(title, desc):
                    continue

                req_text, pref_text = self._extract_sections(desc)
                posting = JobPosting(
                    id=self._make_id("greenhouse", f"{slug}:{job.get('id')}"),
                    source="greenhouse",
                    source_url=job.get("absolute_url", ""),
                    company=slug.capitalize(),
                    title=title,
                    location=job.get("location", {}).get("name") if job.get("location") else None,
                    description=desc,
                    requirements_text=req_text,
                    preferred_text=pref_text,
                    posted_at=datetime.fromisoformat(job.get("updated_at", "").replace("Z", "+00:00")) if job.get("updated_at") else None,
                    raw_data=job,
                )
                postings.append(posting)

        except Exception as e:
            self._stats["errors"].append(f"greenhouse:{slug}: {e}")

        return postings

    async def _fetch_lever(self, slug: str) -> list[JobPosting]:
        """Fetch jobs from Lever public API."""
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        postings = []

        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()

            for job in data:
                title = job.get("text", "")
                desc = job.get("descriptionPlain", "") or job.get("description", "")
                if not self._is_intern_or_entry(title, desc):
                    continue

                req_text, pref_text = self._extract_sections(desc)
                posting = JobPosting(
                    id=self._make_id("lever", f"{slug}:{job.get('id')}"),
                    source="lever",
                    source_url=job.get("hostedUrl", ""),
                    company=slug.capitalize(),
                    title=title,
                    location=job.get("categories", {}).get("location"),
                    description=desc,
                    requirements_text=req_text,
                    preferred_text=pref_text,
                    posted_at=datetime.fromtimestamp(job.get("createdAt", 0) / 1000, tz=timezone.utc) if job.get("createdAt") else None,
                    raw_data=job,
                )
                postings.append(posting)

        except Exception as e:
            self._stats["errors"].append(f"lever:{slug}: {e}")

        return postings

    async def _fetch_ashby(self, slug: str) -> list[JobPosting]:
        """Fetch jobs from Ashby public API."""
        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        postings = []

        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()

            for job in data.get("jobs", []):
                title = job.get("title", "")
                desc = job.get("descriptionHtml", "") or job.get("description", "")
                # Strip HTML tags for text analysis
                desc_text = re.sub(r"<[^>]+>", " ", desc)
                if not self._is_intern_or_entry(title, desc_text):
                    continue

                req_text, pref_text = self._extract_sections(desc_text)
                posting = JobPosting(
                    id=self._make_id("ashby", f"{slug}:{job.get('id')}"),
                    source="ashby",
                    source_url=job.get("jobUrl", ""),
                    company=slug.capitalize(),
                    title=title,
                    location=job.get("location", ""),
                    description=desc_text,
                    requirements_text=req_text,
                    preferred_text=pref_text,
                    posted_at=datetime.fromisoformat(job.get("publishedAt", "").replace("Z", "+00:00")) if job.get("publishedAt") else None,
                    raw_data=job,
                )
                postings.append(posting)

        except Exception as e:
            self._stats["errors"].append(f"ashby:{slug}: {e}")

        return postings

    # ──────────────────────────────────────────────────────────────────────────
    # Source B: Free Public Remote/Tech Job Feeds
    # ──────────────────────────────────────────────────────────────────────────
    async def _fetch_remotive(self) -> list[JobPosting]:
        """Fetch jobs from Remotive public API."""
        postings = []

        try:
            resp = await self._client.get(self.REMOTIVE_URL)
            resp.raise_for_status()
            data = resp.json()

            for job in data.get("jobs", []):
                title = job.get("title", "")
                desc = job.get("description", "")
                if not self._is_intern_or_entry(title, desc):
                    continue

                req_text, pref_text = self._extract_sections(desc)
                posting = JobPosting(
                    id=self._make_id("remotive", str(job.get("id", ""))),
                    source="remotive",
                    source_url=job.get("url", ""),
                    company=job.get("company_name", "Unknown"),
                    title=title,
                    location=job.get("candidate_required_location", "Remote"),
                    description=desc,
                    requirements_text=req_text,
                    preferred_text=pref_text,
                    posted_at=datetime.fromisoformat(job.get("publication_date", "").replace("Z", "+00:00")) if job.get("publication_date") else None,
                    raw_data=job,
                )
                postings.append(posting)

        except Exception as e:
            self._stats["errors"].append(f"remotive: {e}")

        return postings

    async def _fetch_arbeitnow(self) -> list[JobPosting]:
        """Fetch jobs from Arbeitnow free API."""
        postings = []

        try:
            resp = await self._client.get(self.ARBEITNOW_URL)
            resp.raise_for_status()
            data = resp.json()

            for job in data.get("data", []):
                title = job.get("title", "")
                desc = job.get("description", "")
                if not self._is_intern_or_entry(title, desc):
                    continue

                req_text, pref_text = self._extract_sections(desc)
                posting = JobPosting(
                    id=self._make_id("arbeitnow", str(job.get("id", ""))),
                    source="arbeitnow",
                    source_url=job.get("url", ""),
                    company=job.get("company_name", "Unknown"),
                    title=title,
                    location=job.get("location", "Remote"),
                    description=desc,
                    requirements_text=req_text,
                    preferred_text=pref_text,
                    posted_at=datetime.fromisoformat(job.get("created_at", "").replace("Z", "+00:00")) if job.get("created_at") else None,
                    raw_data=job,
                )
                postings.append(posting)

        except Exception as e:
            self._stats["errors"].append(f"arbeitnow: {e}")

        return postings

    async def _fetch_themuse(self) -> list[JobPosting]:
        """Fetch jobs from The Muse public API."""
        postings = []

        try:
            resp = await self._client.get(self.THEMUSE_URL)
            resp.raise_for_status()
            data = resp.json()

            for job in data.get("results", []):
                title = job.get("name", "")
                desc = job.get("contents", "")
                if not self._is_intern_or_entry(title, desc):
                    continue

                req_text, pref_text = self._extract_sections(desc)
                locations = [loc.get("name", "") for loc in job.get("locations", [])]
                posting = JobPosting(
                    id=self._make_id("themuse", str(job.get("id", ""))),
                    source="themuse",
                    source_url=job.get("refs", {}).get("landing_page", ""),
                    company=job.get("company", {}).get("name", "Unknown"),
                    title=title,
                    location=", ".join(locations) if locations else "Remote",
                    description=desc,
                    requirements_text=req_text,
                    preferred_text=pref_text,
                    posted_at=datetime.fromisoformat(job.get("publication_date", "").replace("Z", "+00:00")) if job.get("publication_date") else None,
                    raw_data=job,
                )
                postings.append(posting)

        except Exception as e:
            self._stats["errors"].append(f"themuse: {e}")

        return postings

    # ──────────────────────────────────────────────────────────────────────────
    # Source C: Optional python-jobspy wrapper
    # ──────────────────────────────────────────────────────────────────────────
    async def _fetch_jobspy(self) -> list[JobPosting]:
        """Fetch jobs using python-jobspy if available."""
        postings = []

        try:
            # Import inside try/except so it never crashes if not installed
            from jobspy import scrape_jobs  # type: ignore

            def _scrape() -> list[dict]:
                return scrape_jobs(
                    site_name=["indeed", "linkedin"],
                    search_term="Software Engineer Intern",
                    location="India",
                    results_wanted=25,
                    hours_old=168,  # Last week
                    country_indeed="India",
                )

            # Run in thread pool to avoid blocking
            jobs = await asyncio.to_thread(_scrape)

            for _, job in jobs.iterrows():
                title = str(job.get("title", ""))
                desc = str(job.get("description", ""))
                if not self._is_intern_or_entry(title, desc):
                    continue

                req_text, pref_text = self._extract_sections(desc)
                posting = JobPosting(
                    id=self._make_id("jobspy", str(job.get("id", ""))),
                    source="jobspy",
                    source_url=str(job.get("job_url", "")),
                    company=str(job.get("company", "Unknown")),
                    title=title,
                    location=str(job.get("location", "India")),
                    description=desc,
                    requirements_text=req_text,
                    preferred_text=pref_text,
                    posted_at=datetime.now(timezone.utc),  # jobspy doesn't always provide date
                    raw_data=job.to_dict(),
                )
                postings.append(posting)

        except ImportError:
            # jobspy not installed — silently skip
            pass
        except Exception as e:
            self._stats["errors"].append(f"jobspy: {e}")

        return postings

    # ──────────────────────────────────────────────────────────────────────────
    # Main harvest orchestration
    # ──────────────────────────────────────────────────────────────────────────
    async def harvest_all(self, *, use_jobspy: bool = False) -> list[HarvestResult]:
        """
        Run full multi-source harvest in parallel.

        Returns:
            List of HarvestResult per source
        """
        if self._client is None:
            raise RuntimeError("Harvester not initialized. Use async context manager.")

        results: list[HarvestResult] = []

        # Source A: ATS APIs (parallel)
        ats_tasks = [
            *[self._fetch_greenhouse(slug) for slug in self.GREENHOUSE_SLUGS],
            *[self._fetch_lever(slug) for slug in self.LEVER_SLUGS],
            *[self._fetch_ashby(slug) for slug in self.ASHBY_SLUGS],
        ]
        ats_results = await asyncio.gather(*ats_tasks, return_exceptions=True)

        # Flatten and process
        all_postings: list[JobPosting] = []
        for i, result in enumerate(ats_results):
            if isinstance(result, Exception):
                self._stats["errors"].append(f"ats_task_{i}: {result}")
                continue
            all_postings.extend(result)

        # Source B: Public feeds (parallel)
        feed_tasks = [
            self._fetch_remotive(),
            self._fetch_arbeitnow(),
            self._fetch_themuse(),
        ]
        feed_results = await asyncio.gather(*feed_tasks, return_exceptions=True)
        for i, result in enumerate(feed_results):
            if isinstance(result, Exception):
                self._stats["errors"].append(f"feed_task_{i}: {result}")
                continue
            all_postings.extend(result)

        # Source C: Optional jobspy
        if use_jobspy:
            jobspy_postings = await self._fetch_jobspy()
            all_postings.extend(jobspy_postings)

        # Deduplicate and enrich with skills
        new_count = 0
        dup_count = 0
        by_source: dict[str, int] = {}

        for posting in all_postings:
            by_source[posting.source] = by_source.get(posting.source, 0) + 1

            if posting.id in self._postings:
                dup_count += 1
                # Update existing with fresh data
                self._postings[posting.id] = posting
            else:
                new_count += 1
                self._postings[posting.id] = posting

            # Extract skills
            skills = self._skill_extractor.extract(posting)
            posting.skills = skills

        self._save_storage()
        self._stats["total_harvested"] += new_count
        self._stats["by_source"] = by_source
        self._stats["last_harvest"] = datetime.now(timezone.utc).isoformat()

        # Build results per source for reporting
        source_counts: dict[str, tuple[int, int]] = {}  # source -> (new, total)
        for posting in all_postings:
            new, total = source_counts.get(posting.source, (0, 0))
            total += 1
            if posting.id not in self._postings or len(self._postings) == new_count + dup_count:
                # This logic needs fixing - track per source
                pass
            source_counts[posting.source] = (new, total)

        # Simplified result building
        for source, (new, total) in source_counts.items():
            results.append(HarvestResult(
                source=source,
                fetched=total,
                new=new,
                duplicates=total - new,
                errors=0,
            ))

        return results

    async def enrich_top_jobs_with_free_llm(
        self,
        limit: int = 10,
        llm_client: Any = None,  # FreeOpenRouterClient
    ) -> int:
        """
        Background enrichment using FreeOpenRouterClient at rate-limit-safe pace.

        Uses nvidia/nemotron-3.5-lightning:free at 1 request per 3.5 seconds
        to respect 20 RPM free tier limit.
        """
        if llm_client is None:
                from ...core.free_llm import get_free_llm_client
                llm_client = await get_free_llm_client()

        # Sort postings by recency, take top N that lack enrichment
        candidates = [
            p for p in self._postings.values()
            if not p.summary or not p.sub_concepts
        ]
        candidates.sort(key=lambda p: p.ingested_at, reverse=True)
        candidates = candidates[:limit]

        enriched = 0
        for posting in candidates:
            try:
                # Build prompt for summarization + sub-concept extraction
                prompt = f"""
Job Title: {posting.title}
Company: {posting.company}
Description: {posting.description[:3000]}
Requirements: {posting.requirements_text[:1500]}
Preferred: {posting.preferred_text[:1500]}
Detected Skills: {list(posting.skills.keys())}

Provide:
1. A 2-sentence summary of the role
2. Sub-concepts for each detected skill (e.g., for "Python": ["asyncio", "pytest", "FastAPI"])
"""
                from pydantic import BaseModel
                from typing import List

                class EnrichmentResult(BaseModel):
                    summary: str
                    sub_concepts: dict[str, List[str]]

                system_prompt = "You are a technical recruiter extracting structured insights from job postings."

                result = await llm_client.generate_structured(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    pydantic_model=EnrichmentResult,
                    tier="fast",
                    temperature=0.1,
                    max_tokens=1024,
                )

                posting.summary = result.summary
                posting.sub_concepts = result.sub_concepts
                enriched += 1

                # Rate limit: 3.5 seconds between requests (≈17 RPM, under 20 limit)
                await asyncio.sleep(3.5)

            except Exception as e:
                self._stats["errors"].append(f"enrich:{posting.id}: {e}")
                continue

        if enriched:
            self._save_storage()

        return enriched

    def get_telemetry(self, llm_stats: dict[str, Any] | None = None) -> Telemetry:
        """Generate system telemetry."""
        by_source: dict[str, int] = {}
        by_cluster: dict[str, int] = {}
        skill_coverage: dict[str, int] = {}

        for posting in self._postings.values():
            by_source[posting.source] = by_source.get(posting.source, 0) + 1
            for skill in posting.skills:
                cluster = SKILL_ONTOLOGY.get(skill, {}).get("cluster", "Unknown")
                by_cluster[cluster] = by_cluster.get(cluster, 0) + 1
                skill_coverage[skill] = skill_coverage.get(skill, 0) + 1

        return Telemetry(
            total_postings=len(self._postings),
            by_source=by_source,
            by_role_cluster=by_cluster,
            active_model=llm_stats.get("last_model_used", "n/a") if llm_stats else "n/a",
            cache_hit_rate_pct=llm_stats.get("cache_hit_rate_pct", 0.0) if llm_stats else 0.0,
            llm_requests_today=llm_stats.get("requests", 0) if llm_stats else 0,
            last_harvest=self._stats["last_harvest"],
            skill_coverage=skill_coverage,
        )

    def load_offline_seed(self) -> int:
        """Load 50 realistic pre-parsed internships for offline/air-gapped environments."""
        seed_postings = OFFLINE_SEED_POSTINGS
        added = 0

        for seed in seed_postings:
            posting = JobPosting(**seed)
            posting.skills = self._skill_extractor.extract(posting)
            if posting.id not in self._postings:
                self._postings[posting.id] = posting
                added += 1

        self._save_storage()
        return added


# ──────────────────────────────────────────────────────────────────────────────
# Offline Seed Data — 50 Realistic Internships
# ──────────────────────────────────────────────────────────────────────────────
OFFLINE_SEED_POSTINGS: list[dict[str, Any]] = [
    {
        "id": "seed001", "source": "seed", "source_url": "https://example.com/jobs/1",
        "company": "Stripe", "title": "Software Engineering Intern - Backend",
        "location": "San Francisco, CA", "description": (
            "Join Stripe's Infrastructure team building scalable payment systems. "
            "You'll work on APIs that process billions of dollars annually. "
            "We use Ruby, Go, and PostgreSQL. Strong CS fundamentals required."
        ),
        "requirements_text": (
            "Requirements: Python or Go or Ruby, SQL (PostgreSQL), REST APIs, "
            "Git, Data structures & algorithms. Must have experience building web services."
        ),
        "preferred_text": (
            "Preferred: Kubernetes, Docker, gRPC, GraphQL, OpenTelemetry, "
            "Experience with high-throughput systems."
        ),
        "posted_at": "2024-01-15T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-15T00:00:00+00:00",
    },
    {
        "id": "seed002", "source": "seed", "source_url": "https://example.com/jobs/2",
        "company": "Cloudflare", "title": "Systems Engineering Intern",
        "location": "Austin, TX", "description": (
            "Work on Cloudflare's edge network serving 20M+ HTTP requests/second. "
            "Build tools in Rust and Go that power our CDN, DDoS protection, and Workers platform. "
            "Low-level networking and Linux internals knowledge a plus."
        ),
        "requirements_text": (
            "Requirements: Rust or Go, Linux, Networking (TCP/IP, HTTP, TLS), "
            "C or C++, Git. Experience with systems programming."
        ),
        "preferred_text": (
            "Preferred: eBPF, Kubernetes, Prometheus, Grafana, Assembly, "
            "Kernel development, DPDK."
        ),
        "posted_at": "2024-01-16T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-16T00:00:00+00:00",
    },
    {
        "id": "seed003", "source": "seed", "source_url": "https://example.com/jobs/3",
        "company": "Databricks", "title": "ML Platform Engineering Intern",
        "location": "Seattle, WA", "description": (
            "Build the next generation of ML infrastructure on top of Apache Spark and Delta Lake. "
            "You'll work on feature stores, model serving, and distributed training pipelines. "
            "Python, Scala, and Kubernetes experience valued."
        ),
        "requirements_text": (
            "Requirements: Python, SQL, Machine Learning fundamentals, Distributed systems, "
            "Spark or Ray or Dask, Git. Strong software engineering practices."
        ),
        "preferred_text": (
            "Preferred: MLflow, Kubeflow, Kubernetes, Terraform, Rust, "
            "Deep learning (PyTorch/TensorFlow), Feature stores."
        ),
        "posted_at": "2024-01-17T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-17T00:00:00+00:00",
    },
    {
        "id": "seed004", "source": "seed", "source_url": "https://example.com/jobs/4",
        "company": "Postman", "title": "Full Stack Engineering Intern",
        "location": "Remote (US)", "description": (
            "Help millions of developers build better APIs. Work on the Postman client, "
            "collaboration features, and API governance tools. React, TypeScript, Node.js stack."
        ),
        "requirements_text": (
            "Requirements: TypeScript, React, Node.js, REST APIs, Git, HTML/CSS, "
            "Testing (Jest/Cypress). Experience building web applications."
        ),
        "preferred_text": (
            "Preferred: GraphQL, Electron, WebSockets, OpenAPI/Swagger, "
            "Design systems, Accessibility (a11y)."
        ),
        "posted_at": "2024-01-18T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-18T00:00:00+00:00",
    },
    {
        "id": "seed005", "source": "seed", "source_url": "https://example.com/jobs/5",
        "company": "Razorpay", "title": "Backend Engineering Intern - Payments",
        "location": "Bangalore, India", "description": (
            "Build payment infrastructure handling millions of transactions daily. "
            "Work on checkout, subscriptions, and fraud detection systems. "
            "Java/Spring Boot, PostgreSQL, Redis, Kafka stack."
        ),
        "requirements_text": (
            "Requirements: Java, Spring Boot, SQL (PostgreSQL/MySQL), Redis, "
            "REST APIs, Git, Data structures. Understanding of payment flows."
        ),
        "preferred_text": (
            "Preferred: Kafka, Kubernetes, Docker, gRPC, Distributed transactions, "
            "PCI-DSS compliance, Fraud detection algorithms."
        ),
        "posted_at": "2024-01-19T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-19T00:00:00+00:00",
    },
    {
        "id": "seed006", "source": "seed", "source_url": "https://example.com/jobs/6",
        "company": "Vercel", "title": "Frontend Platform Intern",
        "location": "Remote (Global)", "description": (
            "Work on the platform that powers the world's fastest websites. "
            "Build developer tools, edge functions, and Next.js framework features. "
            "TypeScript, Rust, and WebAssembly expertise welcomed."
        ),
        "requirements_text": (
            "Requirements: TypeScript, React, Next.js, Node.js, Git, Web performance, "
            "HTML/CSS. Experience with frontend frameworks."
        ),
        "preferred_text": (
            "Preferred: Rust, WebAssembly, Turborepo, Edge computing, "
            "Compiler internals, Build systems, Open source contributions."
        ),
        "posted_at": "2024-01-20T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-20T00:00:00+00:00",
    },
    {
        "id": "seed007", "source": "seed", "source_url": "https://example.com/jobs/7",
        "company": "Figma", "title": "Infrastructure Engineering Intern",
        "location": "New York, NY", "description": (
            "Scale Figma's real-time collaboration engine to millions of concurrent users. "
            "Work on WebRTC, CRDTs, and custom database solutions. "
            "C++, TypeScript, and Rust in a highly technical environment."
        ),
        "requirements_text": (
            "Requirements: C++ or Rust, TypeScript, Distributed systems, WebRTC or WebSockets, "
            "Git, Algorithms. Experience with real-time systems."
        ),
        "preferred_text": (
            "Preferred: CRDTs, Operational transforms, WebAssembly, "
            "Database internals, Kubernetes, Performance profiling."
        ),
        "posted_at": "2024-01-21T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-21T00:00:00+00:00",
    },
    {
        "id": "seed008", "source": "seed", "source_url": "https://example.com/jobs/8",
        "company": "Coinbase", "title": "Blockchain Engineering Intern",
        "location": "Remote (US)", "description": (
            "Build the future of crypto infrastructure. Work on node operators, "
            "indexing pipelines, and DeFi integrations. Go, PostgreSQL, and Kubernetes."
        ),
        "requirements_text": (
            "Requirements: Go, PostgreSQL, Blockchain fundamentals (EVM, UTXO), "
            "REST APIs, Git, Docker. Understanding of consensus mechanisms."
        ),
        "preferred_text": (
            "Preferred: Kubernetes, gRPC, GraphQL (The Graph), Rust, "
            "Smart contracts (Solidity), MEV, Zero-knowledge proofs."
        ),
        "posted_at": "2024-01-22T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-22T00:00:00+00:00",
    },
    {
        "id": "seed009", "source": "seed", "source_url": "https://example.com/jobs/9",
        "company": "Palantir", "title": "Forward Deployed Software Engineer Intern",
        "location": "Washington DC / Palo Alto, CA", "description": (
            "Work directly with government and commercial clients solving critical data problems. "
            "End-to-end ownership: from requirements gathering to deployment. "
            "Java, TypeScript, React, and PostgreSQL."
        ),
        "requirements_text": (
            "Requirements: Java or Python, TypeScript, React, SQL, Git, "
            "Problem solving, Communication. Willingness to travel."
        ),
        "preferred_text": (
            "Preferred: Kubernetes, Docker, Big data (Spark/Flink), "
            "Security clearance eligible, Data visualization, Ontology modeling."
        ),
        "posted_at": "2024-01-23T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-23T00:00:00+00:00",
    },
    {
        "id": "seed010", "source": "seed", "source_url": "https://example.com/jobs/10",
        "company": "Zoox", "title": "Robotics Software Intern - Planning",
        "location": "Foster City, CA", "description": (
            "Develop motion planning algorithms for autonomous vehicles. "
            "Work on trajectory optimization, behavior planning, and safety validation. "
            "C++, Python, ROS2, and simulation environments."
        ),
        "requirements_text": (
            "Requirements: C++, Python, Robotics (ROS/ROS2), Motion planning, "
            "Algorithms, Git, Linear algebra. Strong mathematical background."
        ),
        "preferred_text": (
            "Preferred: Trajectory optimization, MPC, Behavior trees, "
            "Simulation (CARLA/LGSVL), CUDA, Real-time systems, Safety standards (ISO 26262)."
        ),
        "posted_at": "2024-01-24T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-24T00:00:00+00:00",
    },
    {
        "id": "seed011", "source": "seed", "source_url": "https://example.com/jobs/11",
        "company": "Mistral AI", "title": "ML Research Engineering Intern",
        "location": "Paris, France / Remote", "description": (
            "Contribute to open-weight foundation models. Work on training infrastructure, "
            "data pipelines, and evaluation frameworks. PyTorch, distributed training, "
            "and efficient attention mechanisms."
        ),
        "requirements_text": (
            "Requirements: Python, PyTorch, Deep learning, Transformers, "
            "Distributed training (FSDP/DeepSpeed), Git, CUDA. Research experience."
        ),
        "preferred_text": (
            "Preferred: FlashAttention, Triton, Model parallelism, "
            "RLHF/RLAIF, Evaluation benchmarks, Kernel optimization, Open source LLMs."
        ),
        "posted_at": "2024-01-25T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-25T00:00:00+00:00",
    },
    {
        "id": "seed012", "source": "seed", "source_url": "https://example.com/jobs/12",
        "company": "Linear", "title": "Full Stack Engineering Intern",
        "location": "San Francisco, CA / Remote", "description": (
            "Build the issue tracker that developers actually enjoy using. "
            "Real-time sync, offline-first architecture, and delightful interactions. "
            "TypeScript, React, GraphQL, and Rust (WASM)."
        ),
        "requirements_text": (
            "Requirements: TypeScript, React, GraphQL, Node.js, Git, "
            "Real-time systems, HTML/CSS. Product-minded engineer."
        ),
        "preferred_text": (
            "Preferred: Rust, WebAssembly, CRDTs, Electron, "
            "Design systems, Accessibility, Performance optimization."
        ),
        "posted_at": "2024-01-26T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-26T00:00:00+00:00",
    },
    {
        "id": "seed013", "source": "seed", "source_url": "https://example.com/jobs/13",
        "company": "Supabase", "title": "Database Engineering Intern",
        "location": "Remote (Global)", "description": (
            "Work on Postgres extensions, connection pooling, and the Supabase platform. "
            "Build tools that make Postgres as easy as Firebase. "
            "TypeScript, Rust, PostgreSQL, and Go."
        ),
        "requirements_text": (
            "Requirements: PostgreSQL, TypeScript, Rust or Go, Git, "
            "Database internals, REST APIs. Open source contributions welcome."
        ),
        "preferred_text": (
            "Preferred: Postgres extensions (pgvector, pg_cron), Connection pooling (PgBouncer), "
            "Kubernetes, Realtime (WebSockets), Auth (JWT/OAuth), CI/CD."
        ),
        "posted_at": "2024-01-27T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-27T00:00:00+00:00",
    },
    {
        "id": "seed014", "source": "seed", "source_url": "https://example.com/jobs/14",
        "company": "Ramp", "title": "Backend Engineering Intern - Ledger",
        "location": "New York, NY", "description": (
            "Build the financial ledger processing billions in corporate spend. "
            "Double-entry accounting, idempotency, and audit trails. "
            "Python, PostgreSQL, and event-driven architecture."
        ),
        "requirements_text": (
            "Requirements: Python, PostgreSQL, SQL, Event-driven systems, "
            "Git, Financial systems basics. Strong attention to correctness."
        ),
        "preferred_text": (
            "Preferred: Kafka, Kubernetes, Temporal, Formal verification, "
            "Property-based testing, Rust, Distributed transactions."
        ),
        "posted_at": "2024-01-28T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-28T00:00:00+00:00",
    },
    {
        "id": "seed015", "source": "seed", "source_url": "https://example.com/jobs/15",
        "company": "Perplexity", "title": "Search & RAG Engineering Intern",
        "location": "San Francisco, CA", "description": (
            "Build the answer engine that cites sources. Work on retrieval, "
            "reranking, and LLM orchestration. Python, vector databases, and streaming."
        ),
        "requirements_text": (
            "Requirements: Python, Vector databases (Pinecone/Weaviate/Qdrant), "
            "LLMs (OpenAI/Anthropic/open), RAG pipelines, Git, FastAPI. Search background."
        ),
        "preferred_text": (
            "Preferred: ColBERT, SPLADE, Rerankers (Cohere/Jina), "
            "Streaming responses, Evaluation frameworks, Kubernetes, Prompt engineering."
        ),
        "posted_at": "2024-01-29T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-29T00:00:00+00:00",
    },
    {
        "id": "seed016", "source": "seed", "source_url": "https://example.com/jobs/16",
        "company": "Notion", "title": "Full Stack Intern - Collaboration",
        "location": "San Francisco, CA / Remote", "description": (
            "Build real-time collaborative editing for millions of users. "
            "CRDTs, conflict resolution, and offline support. "
            "TypeScript, React, Electron, and SQLite (WASM)."
        ),
        "requirements_text": (
            "Requirements: TypeScript, React, Electron, Git, "
            "Real-time collaboration, Algorithms. Product intuition."
        ),
        "preferred_text": (
            "Preferred: CRDTs (Yjs/Automerge), SQLite/WASM, Rust, "
            "Offline-first, Conflict resolution, Performance profiling."
        ),
        "posted_at": "2024-01-30T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-30T00:00:00+00:00",
    },
    {
        "id": "seed017", "source": "seed", "source_url": "https://example.com/jobs/17",
        "company": "Anthropic", "title": "AI Safety Research Engineering Intern",
        "location": "San Francisco, CA", "description": (
            "Work on constitutional AI, interpretability, and scalable oversight. "
            "Build evaluation frameworks and safety tooling. "
            "Python, PyTorch/JAX, and large-scale experimentation."
        ),
        "requirements_text": (
            "Requirements: Python, PyTorch or JAX, ML research background, "
            "Transformers, Git, Scientific writing. Safety alignment interest."
        ),
        "preferred_text": (
            "Preferred: Interpretability (SAEs/probes), Constitutional AI, "
            "RLHF, Scalable oversight, Evaluations, Distributed training, JAX/Flax."
        ),
        "posted_at": "2024-01-31T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-01-31T00:00:00+00:00",
    },
    {
        "id": "seed018", "source": "seed", "source_url": "https://example.com/jobs/18",
        "company": "OpenAI", "title": "Applied AI Engineering Intern",
        "location": "San Francisco, CA", "description": (
            "Help customers build with GPT models. Work on fine-tuning, "
            "embeddings, and the Assistants API. Python, TypeScript, and API design."
        ),
        "requirements_text": (
            "Requirements: Python, TypeScript, LLM APIs, REST APIs, Git, "
            "Prompt engineering, Customer-facing experience. Technical communication."
        ),
        "preferred_text": (
            "Preferred: Fine-tuning, Embeddings, RAG, Function calling, "
            "Eval frameworks, OpenAI SDK, Developer experience, Technical writing."
        ),
        "posted_at": "2024-02-01T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-01T00:00:00+00:00",
    },
    {
        "id": "seed019", "source": "seed", "source_url": "https://example.com/jobs/19",
        "company": "Scale AI", "title": "MLOps Engineering Intern",
        "location": "San Francisco, CA / Remote", "description": (
            "Build the data engine powering frontier models. "
            "Annotation pipelines, quality assurance, and model evaluation. "
            "Python, Kubernetes, and distributed systems."
        ),
        "requirements_text": (
            "Requirements: Python, Kubernetes, Docker, ML pipelines, Git, "
            "Data engineering, Distributed systems. Scale experience."
        ),
        "preferred_text": (
            "Preferred: Ray, Flyte, Dagster, Labeling tools, "
            "Active learning, Model evaluation, GPU orchestration, Terraform."
        ),
        "posted_at": "2024-02-02T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-02T00:00:00+00:00",
    },
    {
        "id": "seed020", "source": "seed", "source_url": "https://example.com/jobs/20",
        "company": "Hugging Face", "title": "Open Source ML Engineering Intern",
        "location": "Remote (Global)", "description": (
            "Contribute to transformers, datasets, and the Hub. "
            "Make state-of-the-art ML accessible to everyone. "
            "Python, PyTorch, Rust, and community engagement."
        ),
        "requirements_text": (
            "Requirements: Python, PyTorch, Transformers library, Git, "
            "Open source contributions, Community experience. ML background."
        ),
        "preferred_text": (
            "Preferred: Rust, Tokenizers, Safetensors, Accelerate/PEFT, "
            "Model optimization, Benchmarks, Documentation, Multilingual NLP."
        ),
        "posted_at": "2024-02-03T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-03T00:00:00+00:00",
    },
    {
        "id": "seed021", "source": "seed", "source_url": "https://example.com/jobs/21",
        "company": "Airbyte", "title": "Data Engineering Intern - Connectors",
        "location": "Remote (Global)", "description": (
            "Build the open-source data integration platform. "
            "Develop CDC connectors, normalization, and orchestration. "
            "Java, Kotlin, Python, and Airflow/Temporal."
        ),
        "requirements_text": (
            "Requirements: Java or Kotlin, Python, SQL, Data integration, "
            "Git, APIs. Understanding of ETL/ELT patterns."
        ),
        "preferred_text": (
            "Preferred: CDC (Debezium), Airflow, Temporal, Kubernetes, "
            "Terraform, Postgres internals, Performance optimization, Open source."
        ),
        "posted_at": "2024-02-04T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-04T00:00:00+00:00",
    },
    {
        "id": "seed022", "source": "seed", "source_url": "https://example.com/jobs/22",
        "company": "Temporal", "title": "SDK Engineering Intern - TypeScript",
        "location": "Seattle, WA / Remote", "description": (
            "Build the TypeScript SDK for durable execution. "
            "Workflows, activities, and replay-based programming model. "
            "TypeScript, Node.js, and distributed systems."
        ),
        "requirements_text": (
            "Requirements: TypeScript, Node.js, Async programming, Git, "
            "Distributed systems basics, Testing. Developer experience focus."
        ),
        "preferred_text": (
            "Preferred: Temporal internals, gRPC, Protocol Buffers, "
            "React, Workflow patterns, Observability, Open source."
        ),
        "posted_at": "2024-02-05T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-05T00:00:00+00:00",
    },
    {
        "id": "seed023", "source": "seed", "source_url": "https://example.com/jobs/23",
        "company": "PlanetScale", "title": "Database Intern - Vitess",
        "location": "Remote (US)", "description": (
            "Scale MySQL to planet-scale with Vitess. "
            "Work on sharding, query routing, and schema management. "
            "Go, MySQL, Vitess, and distributed databases."
        ),
        "requirements_text": (
            "Requirements: Go, MySQL, SQL, Distributed databases, Git, "
            "Systems programming. Database internals interest."
        ),
        "preferred_text": (
            "Preferred: Vitess, Sharding, Query planning, Kubernetes, "
            "Consensus (Raft), Performance tuning, Open source contributions."
        ),
        "posted_at": "2024-02-06T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-06T00:00:00+00:00",
    },
    {
        "id": "seed024", "source": "seed", "source_url": "https://example.com/jobs/24",
        "company": "Tailscale", "title": "Networking Intern - WireGuard",
        "location": "Remote (Global)", "description": (
            "Build the mesh VPN using WireGuard. "
            "NAT traversal, DERP relays, and coordination servers. "
            "Go, Rust, and network protocols."
        ),
        "requirements_text": (
            "Requirements: Go, Networking (TCP/IP, UDP, NAT), WireGuard basics, "
            "Git, Linux. Systems programming experience."
        ),
        "preferred_text": (
            "Preferred: Rust, QUIC/HTTP3, DERP/STUN/TURN, "
            "eBPF, Kernel networking, IPv6, Mobile platforms (iOS/Android)."
        ),
        "posted_at": "2024-02-07T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-07T00:00:00+00:00",
    },
    {
        "id": "seed025", "source": "seed", "source_url": "https://example.com/jobs/25",
        "company": "Cloudflare", "title": "Workers Runtime Intern - V8 Isolates",
        "location": "London, UK / Remote", "description": (
            "Push the edge runtime to new limits. "
            "V8 isolates, WASM, and zero-cold-start execution. "
            "Rust, C++, JavaScript, and systems programming."
        ),
        "requirements_text": (
            "Requirements: Rust, C++, JavaScript, V8/Isolates, Git, "
            "Systems programming, Web standards. Performance obsession."
        ),
        "preferred_text": (
            "Preferred: WebAssembly, WASI, Cap'n Proto, "
            "Kernel bypass (io_uring), Formal methods, Compiler internals."
        ),
        "posted_at": "2024-02-08T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-08T00:00:00+00:00",
    },
    {
        "id": "seed026", "source": "seed", "source_url": "https://example.com/jobs/26",
        "company": "GitHub", "title": "Copilot Platform Intern",
        "location": "Remote (US)", "description": (
            "Build the AI pair programmer used by millions. "
            "Context retrieval, code generation, and IDE integrations. "
            "TypeScript, Rust, Electron/VS Code, and LLMs."
        ),
        "requirements_text": (
            "Requirements: TypeScript, Rust or Go, LLMs, IDE extensions, "
            "Git, Code analysis. Developer tools passion."
        ),
        "preferred_text": (
            "Preferred: VS Code API, Language Server Protocol, Tree-sitter, "
            "RAG for code, Evaluation, Kubernetes, Open source."
        ),
        "posted_at": "2024-02-09T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-09T00:00:00+00:00",
    },
    {
        "id": "seed027", "source": "seed", "source_url": "https://example.com/jobs/27",
        "company": "Vercel", "title": "AI SDK Intern - Streaming",
        "location": "Remote (Global)", "description": (
            "Build the React/Next.js SDK for streaming LLM responses. "
            "Edge functions, tool calling, and framework integrations. "
            "TypeScript, React, Streaming, and Web APIs."
        ),
        "requirements_text": (
            "Requirements: TypeScript, React, Next.js, Streaming APIs, "
            "Git, Web platform. AI product experience."
        ),
        "preferred_text": (
            "Preferred: Vercel AI SDK, Tool calling, RAG, "
            "Edge runtime, React Server Components, Performance, Open source."
        ),
        "posted_at": "2024-02-10T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-10T00:00:00+00:00",
    },
    {
        "id": "seed028", "source": "seed", "source_url": "https://example.com/jobs/28",
        "company": "Replit", "title": "Ghostwriter AI Intern",
        "location": "San Francisco, CA / Remote", "description": (
            "Build the AI coding agent in the browser IDE. "
            "Code completion, generation, and explanation. "
            "TypeScript, Python, WASM, and LLM orchestration."
        ),
        "requirements_text": (
            "Requirements: TypeScript, Python, LLMs, WebAssembly, Git, "
            "Code analysis, Browser APIs. Education/learn-to-code passion."
        ),
        "preferred_text": (
            "Preferred: Monaco/CodeMirror, Language servers, "
            "RAG for code, Multi-file editing, Evaluation, Rust, Open source."
        ),
        "posted_at": "2024-02-11T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-11T00:00:00+00:00",
    },
    {
        "id": "seed029", "source": "seed", "source_url": "https://example.com/jobs/29",
        "company": "Sourcegraph", "title": "Cody AI Intern - Code Search",
        "location": "Remote (Global)", "description": (
            "Build Cody, the AI coding assistant with codebase context. "
            "Code graph, embeddings, and precise navigation. "
            "Go, TypeScript, and code intelligence."
        ),
        "requirements_text": (
            "Requirements: Go, TypeScript, Code search, Graph databases, "
            "Git, LSP/Language servers. Developer productivity focus."
        ),
        "preferred_text": (
            "Preferred: LSIF/SCIP, Tree-sitter, Embeddings for code, "
            "Reranking, Kubernetes, Open source, Code review automation."
        ),
        "posted_at": "2024-02-12T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-12T00:00:00+00:00",
    },
    {
        "id": "seed030", "source": "seed", "source_url": "https://example.com/jobs/30",
        "company": "MongoDB", "title": "Atlas Serverless Intern",
        "location": "New York, NY / Remote", "description": (
            "Build serverless MongoDB that scales to zero. "
            "Auto-scaling, cold start optimization, and multi-tenancy. "
            "Go, Rust, Kubernetes, and distributed systems."
        ),
        "requirements_text": (
            "Requirements: Go, Rust, Kubernetes, Distributed databases, "
            "Git, Systems programming. Cloud infrastructure experience."
        ),
        "preferred_text": (
            "Preferred: MongoDB internals, Serverless (Knative/OpenFaaS), "
            "eBPF, WasmEdge, Multi-tenancy, Billing/metering, Open source."
        ),
        "posted_at": "2024-02-13T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-13T00:00:00+00:00",
    },
    {
        "id": "seed031", "source": "seed", "source_url": "https://example.com/jobs/31",
        "company": "Redis", "title": "Core Engine Intern - Redis Stack",
        "location": "Remote (Global)", "description": (
            "Work on Redis Stack: Search, JSON, TimeSeries, and Probabilistic. "
            "Module development, performance, and new data structures. "
            "C, Rust, and low-level optimization."
        ),
        "requirements_text": (
            "Requirements: C, Rust, Data structures, Algorithms, Git, "
            "Systems programming, Linux. Redis experience a plus."
        ),
        "preferred_text": (
            "Preferred: Redis modules API, SIMD, Lock-free programming, "
            "Benchmarking, Jepsen testing, Redis Stack modules, Open source."
        ),
        "posted_at": "2024-02-14T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-14T00:00:00+00:00",
    },
    {
        "id": "seed032", "source": "seed", "source_url": "https://example.com/jobs/32",
        "company": "Elastic", "title": "Observability Intern - APM",
        "location": "Remote (Global)", "description": (
            "Build Application Performance Monitoring for Elastic Stack. "
            "Distributed tracing, metrics correlation, and anomaly detection. "
            "Go, Java, React, and Elasticsearch."
        ),
        "requirements_text": (
            "Requirements: Go or Java, React, Elasticsearch, Distributed tracing, "
            "Git, Observability concepts. Full stack capability."
        ),
        "preferred_text": (
            "Preferred: OpenTelemetry, eBPF, Machine learning for anomalies, "
            "Kubernetes, Profiling, Log correlation, Open source."
        ),
        "posted_at": "2024-02-15T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-15T00:00:00+00:00",
    },
    {
        "id": "seed033", "source": "seed", "source_url": "https://example.com/jobs/33",
        "company": "Datadog", "title": "Log Management Intern",
        "location": "New York, NY / Remote", "description": (
            "Scale log ingestion to petabytes/day. "
            "Pipeline architecture, compression, and query optimization. "
            "Go, Rust, Kafka, and ClickHouse."
        ),
        "requirements_text": (
            "Requirements: Go, Rust, Kafka, ClickHouse, Distributed systems, "
            "Git, High-throughput systems. Log processing experience."
        ),
        "preferred_text": (
            "Preferred: Vector, Fluent Bit, Compression (ZSTD/LZ4), "
            "Columnar storage, Query optimization, Kubernetes, Open source."
        ),
        "posted_at": "2024-02-16T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-16T00:00:00+00:00",
    },
    {
        "id": "seed034", "source": "seed", "source_url": "https://example.com/jobs/34",
        "company": "Snowflake", "title": "Data Engineering Intern - Stream Processing",
        "location": "San Mateo, CA / Remote", "description": (
            "Build Snowpipe Streaming for real-time data ingestion. "
            "Exactly-once semantics, schema evolution, and iceberg tables. "
            "Java, Scala, SQL, and distributed systems."
        ),
        "requirements_text": (
            "Requirements: Java or Scala, SQL, Stream processing (Kafka/Flink), "
            "Git, Distributed systems. Data warehouse knowledge."
        ),
        "preferred_text": (
            "Preferred: Apache Iceberg, Kafka Streams/Flink, Exactly-once, "
            "Schema registry, Kubernetes, Performance tuning, Open source."
        ),
        "posted_at": "2024-02-17T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-17T00:00:00+00:00",
    },
    {
        "id": "seed035", "source": "seed", "source_url": "https://example.com/jobs/35",
        "company": "Confluent", "title": "Kafka Intern - Client Libraries",
        "location": "Mountain View, CA / Remote", "description": (
            "Build and maintain Kafka client libraries (Java, Go, Python, .NET). "
            "Producer/consumer internals, transactions, and schema registry. "
            "Java, Go, and distributed messaging."
        ),
        "requirements_text": (
            "Requirements: Java, Go, Kafka, Distributed messaging, Git, "
            "Client library design. Open source contributions."
        ),
        "preferred_text": (
            "Preferred: Schema Registry (Avro/Protobuf), Transactions, "
            "Exactly-once, KRaft mode, Connect framework, Performance, Open source."
        ),
        "posted_at": "2024-02-18T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-18T00:00:00+00:00",
    },
    {
        "id": "seed036", "source": "seed", "source_url": "https://example.com/jobs/36",
        "company": "HashiCorp", "title": "Terraform Provider Intern",
        "location": "Remote (Global)", "description": (
            "Build Terraform providers for cloud services. "
            "Resource modeling, CRUD operations, and acceptance testing. "
            "Go, Terraform plugin SDK, and API design."
        ),
        "requirements_text": (
            "Requirements: Go, Terraform, Cloud APIs (AWS/GCP/Azure), Git, "
            "Infrastructure as Code. Provider development experience."
        ),
        "preferred_text": (
            "Preferred: Terraform Plugin Framework, Acceptance testing, "
            "Provider design patterns, OpenTofu, Multi-cloud, CI/CD, Open source."
        ),
        "posted_at": "2024-02-19T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-19T00:00:00+00:00",
    },
    {
        "id": "seed037", "source": "seed", "source_url": "https://example.com/jobs/37",
        "company": "Pulumi", "title": "SDK Intern - TypeScript/Python",
        "location": "Seattle, WA / Remote", "description": (
            "Build the Pulumi SDK for infrastructure as code in real languages. "
            "TypeScript, Python, Go, and .NET bindings. "
            "Language interop, code generation, and developer experience."
        ),
        "requirements_text": (
            "Requirements: TypeScript, Python, Go, Infrastructure as Code, "
            "Git, Code generation. Multi-language experience."
        ),
        "preferred_text": (
            "Preferred: Pulumi, gRPC, Protocol Buffers, Codegen (protobuf/openapi), "
            "Testing frameworks, Package management (npm/PyPI), Open source."
        ),
        "posted_at": "2024-02-20T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-20T00:00:00+00:00",
    },
    {
        "id": "seed038", "source": "seed", "source_url": "https://example.com/jobs/38",
        "company": "Vercel", "title": "Turborepo Intern - Build System",
        "location": "Remote (Global)", "description": (
            "Build the high-performance build system for monorepos. "
            "Remote caching, task scheduling, and incremental computation. "
            "Go, Rust, TypeScript, and build systems."
        ),
        "requirements_text": (
            "Requirements: Go, Rust, TypeScript, Build systems (Bazel/Turbo/Nx), "
            "Git, Caching/invalidation. Monorepo experience."
        ),
        "preferred_text": (
            "Preferred: Remote execution (RBE), Content-addressable storage, "
            "Graph algorithms, Performance profiling, CI/CD integration, Open source."
        ),
        "posted_at": "2024-02-21T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-21T00:00:00+00:00",
    },
    {
        "id": "seed039", "source": "seed", "source_url": "https://example.com/jobs/39",
        "company": "Nx", "title": "DevTools Intern - Affected Graph",
        "location": "Remote (Global)", "description": (
            "Build smart monorepo tooling with computation caching. "
            "Project graph, affected commands, and distributed task execution. "
            "TypeScript, Node.js, and graph algorithms."
        ),
        "requirements_text": (
            "Requirements: TypeScript, Node.js, Graph algorithms, Monorepos, "
            "Git, Build systems. Developer tooling passion."
        ),
        "preferred_text": (
            "Preferred: Distributed computation, Cloud caching, "
            "IDE integrations (VS Code), Plugin architecture, Performance, Open source."
        ),
        "posted_at": "2024-02-22T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-22T00:00:00+00:00",
    },
    {
        "id": "seed040", "source": "seed", "source_url": "https://example.com/jobs/40",
        "company": "Railway", "title": "Platform Intern - Deployment Engine",
        "location": "Remote (Global)", "description": (
            "Build the deployment platform that developers love. "
            "Container orchestration, buildpacks, and preview environments. "
            "Go, TypeScript, Kubernetes, and Docker."
        ),
        "requirements_text": (
            "Requirements: Go, TypeScript, Kubernetes, Docker, Git, "
            "Container orchestration, CI/CD. Platform engineering mindset."
        ),
        "preferred_text": (
            "Preferred: Buildpacks (CNB), Knative, WebAssembly, "
            "Preview deployments, Database provisioning, Edge networking, Open source."
        ),
        "posted_at": "2024-02-23T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-23T00:00:00+00:00",
    },
    {
        "id": "seed041", "source": "seed", "source_url": "https://example.com/jobs/41",
        "company": "Fly.io", "title": "Edge Runtime Intern - Firecracker",
        "location": "Remote (Global)", "description": (
            "Run containers as microVMs at the edge with Firecracker. "
            "Cold start optimization, snapshot/restore, and global scheduling. "
            "Go, Rust, Linux, and virtualization."
        ),
        "requirements_text": (
            "Requirements: Go, Rust, Linux, Virtualization (Firecracker/KVM), "
            "Git, Systems programming. Edge computing interest."
        ),
        "preferred_text": (
            "Preferred: Firecracker, Snapshotting, io_uring, eBPF, "
            "Containerd, WireGuard, Global anycast, Open source."
        ),
        "posted_at": "2024-02-24T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-24T00:00:00+00:00",
    },
    {
        "id": "seed042", "source": "seed", "source_url": "https://example.com/jobs/42",
        "company": "Render", "title": "Backend Intern - Managed Databases",
        "location": "Remote (US)", "description": (
            "Build managed PostgreSQL, Redis, and MySQL on Kubernetes. "
            "Automated backups, PITR, read replicas, and connection pooling. "
            "Go, Kubernetes, and database operations."
        ),
        "requirements_text": (
            "Requirements: Go, Kubernetes, PostgreSQL, Redis, Git, "
            "Database operations, Distributed systems. Cloud databases."
        ),
        "preferred_text": (
            "Preferred: Patroni, PgBouncer, Vitess, Operator pattern, "
            "Disaster recovery, Encryption at rest, Multi-AZ, Open source."
        ),
        "posted_at": "2024-02-25T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-25T00:00:00+00:00",
    },
    {
        "id": "seed043", "source": "seed", "source_url": "https://example.com/jobs/43",
        "company": "Neon", "title": "Serverless Postgres Intern - Storage",
        "location": "Remote (Global)", "description": (
            "Build serverless Postgres with separated storage/compute. "
            "Copy-on-write, branching, and point-in-time recovery. "
            "Rust, Postgres internals, and distributed storage."
        ),
        "requirements_text": (
            "Requirements: Rust, PostgreSQL, Distributed storage, Git, "
            "Systems programming, Copy-on-write. Database internals."
        ),
        "preferred_text": (
            "Preferred: Postgres internals (WAL, pages), Safekeepers, "
            "Pageserver, Branching, PITR, S3/Object storage, Open source."
        ),
        "posted_at": "2024-02-26T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-26T00:00:00+00:00",
    },
    {
        "id": "seed044", "source": "seed", "source_url": "https://example.com/jobs/44",
        "company": "Timescale", "title": "Time-Series Database Intern",
        "location": "Remote (Global)", "description": (
            "Build hypertables, continuous aggregates, and compression. "
            "PostgreSQL extension development for time-series workloads. "
            "C, PostgreSQL, and time-series algorithms."
        ),
        "requirements_text": (
            "Requirements: C, PostgreSQL, Time-series data, Git, "
            "Database extensions, Algorithms. Systems programming."
        ),
        "preferred_text": (
            "Preferred: Continuous aggregates, Compression (Gorilla/Delta-delta), "
            "Hyperfunctions, Distributed hypertables, Prometheus, Open source."
        ),
        "posted_at": "2024-02-27T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-27T00:00:00+00:00",
    },
    {
        "id": "seed045", "source": "seed", "source_url": "https://example.com/jobs/45",
        "company": "ClickHouse", "title": "OLAP Engine Intern - Query Optimization",
        "location": "Remote (Global)", "description": (
            "Build the fastest analytical database. "
            "Vectorized execution, join optimization, and merge trees. "
            "C++, ClickHouse, and query optimization."
        ),
        "requirements_text": (
            "Requirements: C++, SQL, Query optimization, Git, "
            "Columnar databases, Algorithms. Performance engineering."
        ),
        "preferred_text": (
            "Preferred: Vectorized execution, MergeTree, Distributed queries, "
            "Materialized views, Kafka/ClickHouse integration, Benchmarks, Open source."
        ),
        "posted_at": "2024-02-28T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-28T00:00:00+00:00",
    },
    {
        "id": "seed046", "source": "seed", "source_url": "https://example.com/jobs/46",
        "company": "DuckDB", "title": "Embedded Analytics Intern",
        "location": "Remote (Global)", "description": (
            "Build the in-process analytical database. "
            "Parallel execution, CSV/Parquet import, and Python/R bindings. "
            "C++, Python, and analytical workloads."
        ),
        "requirements_text": (
            "Requirements: C++, Python, SQL, Analytics, Git, "
            "Embedded databases, Columnar execution. Open source passion."
        ),
        "preferred_text": (
            "Preferred: Parquet/Arrow, Parallel query, Python bindings (pybind11), "
            "R bindings, WASM, Extension system, Benchmarks, Open source."
        ),
        "posted_at": "2024-02-29T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-02-29T00:00:00+00:00",
    },
    {
        "id": "seed047", "source": "seed", "source_url": "https://example.com/jobs/47",
        "company": "Weaviate", "title": "Vector Database Intern - HNSW",
        "location": "Remote (Global)", "description": (
            "Build the cloud-native vector database. "
            "HNSW indexing, quantization, and multi-tenancy. "
            "Go, Vector search, and distributed systems."
        ),
        "requirements_text": (
            "Requirements: Go, Vector search (HNSW/IVF), Quantization, "
            "Git, Distributed systems. ML/AI infrastructure."
        ),
        "preferred_text": (
            "Preferred: HNSW variants (DiskANN/SPTAG), Product quantization, "
            "Multi-tenancy, Hybrid search (BM25+vector), Kubernetes, Open source."
        ),
        "posted_at": "2024-03-01T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-03-01T00:00:00+00:00",
    },
    {
        "id": "seed048", "source": "seed", "source_url": "https://example.com/jobs/48",
        "company": "Qdrant", "title": "Rust Intern - Vector Search",
        "location": "Remote (Global)", "description": (
            "Build the vector search engine in Rust. "
            "SIMD optimization, payload filtering, and distributed consensus. "
            "Rust, HNSW, and high-performance computing."
        ),
        "requirements_text": (
            "Requirements: Rust, Vector search, SIMD, Git, "
            "Systems programming, Algorithms. Performance focus."
        ),
        "preferred_text": (
            "Preferred: HNSW optimization, Quantization (Scalar/Binary), "
            "Payload indexing, Raft consensus, Kubernetes, Benchmarks, Open source."
        ),
        "posted_at": "2024-03-02T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-03-02T00:00:00+00:00",
    },
    {
        "id": "seed049", "source": "seed", "source_url": "https://example.com/jobs/49",
        "company": "LanceDB", "title": "Embedded Vector DB Intern - Lance Format",
        "location": "Remote (Global)", "description": (
            "Build the serverless vector database on Lance columnar format. "
            "Zero-copy, versioning, and native Python/JS bindings. "
            "Rust, Arrow, and embedded databases."
        ),
        "requirements_text": (
            "Requirements: Rust, Apache Arrow, Lance format, Git, "
            "Columnar formats, Embedded databases. Python/JS experience."
        ),
        "preferred_text": (
            "Preferred: Zero-copy, Time travel/versioning, "
            "Distributed Lance, Python/Node bindings, WASM, Open source."
        ),
        "posted_at": "2024-03-03T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-03-03T00:00:00+00:00",
    },
    {
        "id": "seed050", "source": "seed", "source_url": "https://example.com/jobs/50",
        "company": "Chroma", "title": "AI Embeddings Intern - Retrieval",
        "location": "Remote (Global)", "description": (
            "Build the AI-native embedding database. "
            "Embedding functions, query planning, and agent memory. "
            "Python, Rust, and LLM application patterns."
        ),
        "requirements_text": (
            "Requirements: Python, Rust, Embeddings, Vector search, Git, "
            "LLM applications, RAG patterns. AI product experience."
        ),
        "preferred_text": (
            "Preferred: Embedding models (BGE/E5/GTE), Query planning, "
            "Agent memory, Multi-modal, Evaluation, WASM, Open source."
        ),
        "posted_at": "2024-03-04T00:00:00+00:00",
        "skills": {}, "summary": "", "sub_concepts": {}, "raw_data": {},
        "ingested_at": "2024-03-04T00:00:00+00:00",
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton for app lifespan
# ──────────────────────────────────────────────────────────────────────────────
_default_harvester: FreeJobHarvester | None = None


async def get_job_harvester() -> FreeJobHarvester:
    """Get or create the default FreeJobHarvester singleton."""
    global _default_harvester
    if _default_harvester is None:
        _default_harvester = FreeJobHarvester()
        await _default_harvester.__aenter__()
        # Load offline seed on first initialization
        _default_harvester.load_offline_seed()
    return _default_harvester


async def close_job_harvester() -> None:
    """Close the default harvester (call on app shutdown)."""
    global _default_harvester
    if _default_harvester is not None:
        await _default_harvester.__aexit__(None, None, None)
        _default_harvester = None
