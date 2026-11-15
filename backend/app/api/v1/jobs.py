"""FastAPI endpoints for free job harvesting and telemetry."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Depends
from pydantic import BaseModel

from backend.app.core.free_llm import get_free_llm_client
from backend.app.core.auth import current_identity
from backend.app.services.free_job_engine import (
    FreeJobHarvester,
    HarvestResult,
    Telemetry,
    get_job_harvester,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


# ──────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ──────────────────────────────────────────────────────────────────────────────
class HarvestRequest(BaseModel):
    """Request to trigger a job harvest."""
    use_jobspy: bool = False
    enrich_with_llm: bool = True
    enrich_limit: int = 10


class HarvestResponse(BaseModel):
    """Response from a harvest operation."""
    total_fetched: int
    total_new: int
    total_duplicates: int
    results: list[HarvestResult]
    enrichment_count: int = 0


class TelemetryResponse(BaseModel):
    """Telemetry response model."""
    total_postings: int
    by_source: dict[str, int]
    by_role_cluster: dict[str, int]
    active_model: str
    cache_hit_rate_pct: float
    llm_requests_today: int
    last_harvest: str | None
    skill_coverage: dict[str, int]


class EnrichRequest(BaseModel):
    """Request to enrich top jobs with LLM."""
    limit: int = 10


class EnrichResponse(BaseModel):
    """Response from enrichment operation."""
    enriched: int


class SeedResponse(BaseModel):
    """Response from loading offline seed."""
    added: int


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/harvest-free", response_model=HarvestResponse)
async def harvest_free_jobs(
    request: HarvestRequest,
    background_tasks: BackgroundTasks,
    identity: dict = Depends(current_identity),
) -> HarvestResponse:
    """
    Trigger live multi-source JSON harvest from free public APIs.

    Sources:
    - Greenhouse, Lever, Ashby (ATS public APIs)
    - Remotive, Arbeitnow, The Muse (free job feeds)
    - Optional: python-jobspy for Indeed/LinkedIn

    Returns count of newly added & deduplicated postings per source.
    """
    harvester = await get_job_harvester()

    # Run harvest
    results = await harvester.harvest_all(use_jobspy=request.use_jobspy)

    # Aggregate totals
    total_fetched = sum(r.fetched for r in results)
    total_new = sum(r.new for r in results)
    total_duplicates = sum(r.duplicates for r in results)

    # Background enrichment with free LLM
    enrichment_count = 0
    if request.enrich_with_llm and total_new > 0:
        enrichment_count = await harvester.enrich_top_jobs_with_free_llm(
            limit=request.enrich_limit,
        )

    return HarvestResponse(
        total_fetched=total_fetched,
        total_new=total_new,
        total_duplicates=total_duplicates,
        results=results,
        enrichment_count=enrichment_count,
    )


@router.get("/telemetry", response_model=TelemetryResponse)
async def get_telemetry() -> TelemetryResponse:
    """
    Get system telemetry including:
    - Active model status
    - Cache hit rate
    - Source breakdown
    - Total postings
    - Skill coverage
    """
    harvester = await get_job_harvester()
    llm_client = await get_free_llm_client()

    llm_stats = llm_client.get_stats()
    telemetry = harvester.get_telemetry(llm_stats)

    return TelemetryResponse(
        total_postings=telemetry.total_postings,
        by_source=telemetry.by_source,
        by_role_cluster=telemetry.by_role_cluster,
        active_model=telemetry.active_model,
        cache_hit_rate_pct=telemetry.cache_hit_rate_pct,
        llm_requests_today=telemetry.llm_requests_today,
        last_harvest=telemetry.last_harvest,
        skill_coverage=telemetry.skill_coverage,
    )


@router.post("/enrich", response_model=EnrichResponse)
async def enrich_jobs(request: EnrichRequest, identity: dict = Depends(current_identity)) -> EnrichResponse:
    """
    Enrich top jobs with free LLM (nvidia/nemotron-3.5-lightning:free).

    Runs at rate-limit-safe pace: 1 request per 3.5 seconds
    to respect OpenRouter's 20 RPM free tier limit.
    """
    harvester = await get_job_harvester()

    enriched = await harvester.enrich_top_jobs_with_free_llm(
        limit=request.limit,
    )

    return EnrichResponse(enriched=enriched)


@router.post("/load-seed", response_model=SeedResponse)
async def load_offline_seed(identity: dict = Depends(current_identity)) -> SeedResponse:
    """
    Load 50 realistic pre-parsed internships for offline/air-gapped environments.

    Guarantees the app boots with rich postings even with zero external internet access.
    """
    harvester = await get_job_harvester()
    added = harvester.load_offline_seed()
    return SeedResponse(added=added)


@router.get("/postings")
async def list_postings(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    source: str | None = Query(None),
    cluster: str | None = Query(None),
    skill: str | None = Query(None),
) -> dict[str, Any]:
    """
    List harvested job postings with optional filters.

    Args:
        limit: Max results to return
        offset: Pagination offset
        source: Filter by source (greenhouse, lever, ashby, remotive, etc.)
        cluster: Filter by role cluster (Backend Engineering, ML & Data, etc.)
        skill: Filter by required skill
    """
    harvester = await get_job_harvester()

    postings = list(harvester._postings.values())

    # Apply filters
    if source:
        postings = [p for p in postings if p.source == source]
    if cluster:
        postings = [
            p for p in postings
            if any(
                harvester._skill_extractor.SKILL_ONTOLOGY.get(s, {}).get("cluster") == cluster
                for s in p.skills
            )
        ]
    if skill:
        postings = [p for p in postings if skill in p.skills]

    # Sort by ingestion time (newest first)
    postings.sort(key=lambda p: p.ingested_at, reverse=True)

    # Paginate
    total = len(postings)
    postings = postings[offset:offset + limit]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "postings": [p.model_dump(mode="json") for p in postings],
    }


@router.get("/postings/{posting_id}")
async def get_posting(posting_id: str) -> dict[str, Any]:
    """Get a single job posting by ID."""
    harvester = await get_job_harvester()

    posting = harvester._postings.get(posting_id)
    if not posting:
        raise HTTPException(status_code=404, detail="Posting not found")

    return posting.model_dump(mode="json")


@router.get("/skills")
async def list_skills() -> dict[str, Any]:
    """List all canonical skills with their clusters and aliases."""
    harvester = await get_job_harvester()

    skills = []
    for skill, info in harvester._skill_extractor.SKILL_ONTOLOGY.items():
        skills.append({
            "skill": skill,
            "cluster": info["cluster"],
            "category": info["category"],
            "aliases": info["aliases"],
        })

    return {
        "skills": skills,
        "clusters": sorted(set(info["cluster"] for info in harvester._skill_extractor.SKILL_ONTOLOGY.values())),
        "total": len(skills),
    }


@router.get("/stats/llm")
async def get_llm_stats() -> dict[str, Any]:
    """Get FreeOpenRouterClient statistics."""
    llm_client = await get_free_llm_client()
    return llm_client.get_stats()
