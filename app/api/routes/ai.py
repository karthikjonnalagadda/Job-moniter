"""AI layer endpoints (Phase 8).

* ``GET  /ai/models``         — catalogued + runtime model state.
* ``GET  /ai/models/health``  — health of every AI component.
* ``GET  /ai/metrics``        — embedding / search / rerank latencies + cache stats.
* ``POST /ai/embed``          — embed arbitrary texts (documents or query).
* ``POST /ai/rerank``         — re-rank stored jobs for a resume version.
* ``POST /ai/vector-search``  — semantic (or hybrid) job search.
* ``POST /ai/skill-gap``      — skill-gap analysis for a resume vs a job.
* ``POST /ai/explain``        — full explainability breakdown for one job.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.ai.metrics import AiMetricsReport
from app.ai.registry import ModelRecord
from app.ai.search import SearchResults
from app.api.deps import (
    AiMetricsServiceDep,
    EmbedderDep,
    EmbeddingCacheDep,
    JobRepositoryDep,
    ModelRegistryDep,
    PipelineDep,
    ResumeEmbeddingServiceDep,
    VectorSearchServiceDep,
)
from app.core.ranking.skill_gap import SkillGap, SkillGapAnalyzer
from app.models.job import Job, MatchDetail

router = APIRouter(tags=["ai"])


# ---- request / response models ----------------------------------------------
class ResumeIn(BaseModel):
    resume_id: str | None = None
    text: str | None = None
    skills: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    max_experience_years: float = 2.0


class EmbedRequest(BaseModel):
    texts: list[str]
    is_query: bool = False
    include_vectors: bool = True


class EmbedResponse(BaseModel):
    model_name: str
    dimensions: int
    count: int
    vectors: list[list[float]] = Field(default_factory=list)


class RerankRequest(BaseModel):
    resume: ResumeIn
    limit: int = 100
    persist: bool = False


class VectorSearchRequest(BaseModel):
    text: str | None = None
    query_vector: list[float] | None = None
    limit: int = 20
    skip: int = 0
    filters: dict[str, object] | None = None
    score_threshold: float = 0.0
    hybrid: bool = False


class SkillGapRequest(BaseModel):
    resume_skills: list[str]
    job_skills: list[str]
    job_technologies: list[str] = Field(default_factory=list)


class ExplainRequest(BaseModel):
    resume: ResumeIn
    job_hash: str
    company_priority: float = 0.5


class ResumeEmbedRequest(BaseModel):
    resume_id: str
    content: str
    label: str | None = None
    skills: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    max_experience_years: float = 2.0
    force: bool = False


class ResumeEmbedResponse(BaseModel):
    resume_id: str
    regenerated: bool  # False = content unchanged, existing vector reused
    dimensions: int
    model_name: str
    content_hash: str


class ModelsResponse(BaseModel):
    active: ModelRecord | None = None
    models: list[ModelRecord] = Field(default_factory=list)


class HealthResponse(BaseModel):
    healthy: bool
    components: dict[str, bool]


# ---- endpoints --------------------------------------------------------------
@router.get("/models", response_model=ModelsResponse)
async def models(registry: ModelRegistryDep) -> ModelsResponse:
    return ModelsResponse(active=registry.active(), models=registry.list())


@router.get("/models/health", response_model=HealthResponse)
async def models_health(
    embedder: EmbedderDep, cache: EmbeddingCacheDep, registry: ModelRegistryDep
) -> HealthResponse:
    embed_ok = await embedder.health_check()
    try:
        await cache.stats()
        cache_ok = True
    except Exception:
        cache_ok = False
    active = registry.active()
    components = {
        "embedding_model": embed_ok,
        "embedding_cache": cache_ok,
        "model_registry": active is not None,
    }
    return HealthResponse(healthy=all(components.values()), components=components)


@router.get("/metrics", response_model=AiMetricsReport)
async def metrics(service: AiMetricsServiceDep) -> AiMetricsReport:
    return await service.build()


@router.post("/embed", response_model=EmbedResponse)
async def embed(request: EmbedRequest, embedder: EmbedderDep) -> EmbedResponse:
    if request.is_query:
        vectors = [await embedder.aembed_query(t) for t in request.texts]
    else:
        vectors = await embedder.aembed_documents(request.texts)
    dims = len(vectors[0]) if vectors else embedder.dimensions
    return EmbedResponse(
        model_name=embedder.model_name,
        dimensions=dims,
        count=len(vectors),
        vectors=vectors if request.include_vectors else [],
    )


@router.post("/rerank", response_model=list[Job])
async def rerank(request: RerankRequest, pipeline: PipelineDep) -> list[Job]:
    resume = pipeline.build_resume_context(
        resume_id=request.resume.resume_id,
        text=request.resume.text,
        skills=request.resume.skills,
        preferred_locations=request.resume.preferred_locations,
        max_experience_years=request.resume.max_experience_years,
    )
    return await pipeline.rerank(resume, limit=request.limit, persist=request.persist)


@router.post("/vector-search", response_model=SearchResults)
async def vector_search(
    request: VectorSearchRequest, service: VectorSearchServiceDep
) -> SearchResults:
    if not request.text and not request.query_vector:
        raise HTTPException(status_code=422, detail="Provide 'text' or 'query_vector'")
    return await service.search(
        text=request.text,
        query_vector=request.query_vector,
        limit=request.limit,
        skip=request.skip,
        filters=request.filters,
        score_threshold=request.score_threshold,
        hybrid=request.hybrid,
    )


@router.post("/skill-gap", response_model=SkillGap)
async def skill_gap(request: SkillGapRequest) -> SkillGap:
    return SkillGapAnalyzer().analyze(
        request.resume_skills,
        request.job_skills,
        job_technologies=request.job_technologies,
    )


@router.post("/explain", response_model=MatchDetail)
async def explain(
    request: ExplainRequest, pipeline: PipelineDep, jobs: JobRepositoryDep
) -> MatchDetail:
    job = await jobs.find_one({"job_hash": request.job_hash})
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{request.job_hash}' not found")
    resume = pipeline.build_resume_context(
        resume_id=request.resume.resume_id,
        text=request.resume.text,
        skills=request.resume.skills,
        preferred_locations=request.resume.preferred_locations,
        max_experience_years=request.resume.max_experience_years,
    )
    ranked = pipeline.rank_jobs([job], resume, company_priority={})
    match = ranked[0].match if ranked else None
    if match is None:
        raise HTTPException(status_code=422, detail="Could not rank job (missing resume signal)")
    return match


@router.post("/resume/embed", response_model=ResumeEmbedResponse)
async def resume_embed(
    request: ResumeEmbedRequest, service: ResumeEmbeddingServiceDep
) -> ResumeEmbedResponse:
    result = await service.embed_resume(
        request.resume_id,
        request.content,
        label=request.label,
        skills=request.skills,
        preferred_locations=request.preferred_locations,
        max_experience_years=request.max_experience_years,
        force=request.force,
    )
    return ResumeEmbedResponse(
        resume_id=result.resume.resume_id,
        regenerated=result.regenerated,
        dimensions=result.resume.dimensions,
        model_name=result.resume.model_name,
        content_hash=result.resume.content_hash,
    )
