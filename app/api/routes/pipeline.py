"""Job processing pipeline endpoints.

* ``POST /pipeline/process``        — normalise → filter → dedup → embed → rank → store.
* ``POST /pipeline/rank``           — re-rank stored jobs for a resume (no re-fetch).
* ``POST /pipeline/deduplicate``    — de-duplicate a supplied batch (no store).
* ``POST /pipeline/extract-skills`` — extract categorised skills from text.
* ``GET  /pipeline/stats``          — stored-job + last-run stats.
* ``GET  /pipeline/history``        — recent pipeline runs.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import JobRepositoryDep, PipelineDep, PipelineRunRepositoryDep
from app.collectors.base import RawJob
from app.core.dedup.detector import DedupResult
from app.core.skills.extractor import ExtractedSkills
from app.models.enums import ATSType, SourceType
from app.models.job import Job
from app.models.pipeline_run import PipelineRun
from app.pipeline.pipeline import ProcessItem

router = APIRouter(tags=["pipeline"])


# ---- request models ---------------------------------------------------------
class RawItemIn(BaseModel):
    external_id: str
    title: str
    company: str
    url: str
    location: str | None = None
    description: str | None = None
    posted: str | None = None  # any freshness format (ISO/epoch/relative)
    source: str = "manual"
    source_type: SourceType = SourceType.ATS
    ats_type: ATSType = ATSType.UNKNOWN
    collector_version: str | None = None
    career_url: str | None = None

    def to_item(self) -> ProcessItem:
        raw = RawJob(
            external_id=self.external_id,
            title=self.title,
            company=self.company,
            url=self.url,
            location=self.location,
            description=self.description,
            raw={"posted": self.posted} if self.posted else {},
        )
        return ProcessItem(
            raw=raw,
            source=self.source,
            source_type=self.source_type,
            ats_type=self.ats_type,
            collector_version=self.collector_version,
            career_url=self.career_url,
        )


class ResumeIn(BaseModel):
    resume_id: str | None = None
    text: str | None = None
    skills: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    max_experience_years: float = 2.0


class ProcessRequest(BaseModel):
    items: list[RawItemIn]
    resume: ResumeIn | None = None
    persist: bool = True
    incremental: bool = False


class RankRequest(BaseModel):
    resume: ResumeIn
    limit: int = 1000
    persist: bool = True


class DeduplicateRequest(BaseModel):
    items: list[RawItemIn]


class ExtractSkillsRequest(BaseModel):
    text: str


# ---- response models --------------------------------------------------------
class ProcessResponse(BaseModel):
    run: PipelineRun
    jobs: list[Job] = Field(default_factory=list)
    dedup: DedupResult | None = None


class PipelineStats(BaseModel):
    total_jobs: int
    ranked_jobs: int
    total_runs: int
    last_run: PipelineRun | None = None


# ---- endpoints --------------------------------------------------------------
@router.post("/process", response_model=ProcessResponse)
async def process(request: ProcessRequest, pipeline: PipelineDep) -> ProcessResponse:
    resume = _resume_context(pipeline, request.resume)
    result = await pipeline.process(
        [item.to_item() for item in request.items],
        resume=resume,
        persist=request.persist,
        incremental=request.incremental,
    )
    return ProcessResponse(run=result.run, jobs=result.jobs, dedup=result.dedup)


@router.post("/rank", response_model=list[Job])
async def rank(request: RankRequest, pipeline: PipelineDep) -> list[Job]:
    resume = _resume_context(pipeline, request.resume)
    assert resume is not None  # RankRequest always has a resume
    return await pipeline.rerank(resume, limit=request.limit, persist=request.persist)


@router.post("/deduplicate", response_model=DedupResult)
async def deduplicate(request: DeduplicateRequest, pipeline: PipelineDep) -> DedupResult:
    result = await pipeline.process(
        [item.to_item() for item in request.items], persist=False
    )
    return result.dedup or DedupResult(unique=len(result.jobs), duplicates=0)


@router.post("/extract-skills", response_model=ExtractedSkills)
async def extract_skills(request: ExtractSkillsRequest, pipeline: PipelineDep) -> ExtractedSkills:
    return pipeline.extract_skills(request.text)


@router.get("/stats", response_model=PipelineStats)
async def stats(
    jobs: JobRepositoryDep, runs: PipelineRunRepositoryDep
) -> PipelineStats:
    total = await jobs.count()
    ranked = await jobs.count({"match": {"$ne": None}})
    recent = await runs.list_recent(limit=1)
    return PipelineStats(
        total_jobs=total,
        ranked_jobs=ranked,
        total_runs=await runs.count(),
        last_run=recent[0] if recent else None,
    )


@router.get("/history", response_model=list[PipelineRun])
async def history(
    runs: PipelineRunRepositoryDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[PipelineRun]:
    return await runs.list_recent(limit=limit)


def _resume_context(pipeline: PipelineDep, resume: ResumeIn | None):  # type: ignore[no-untyped-def]
    if resume is None:
        return None
    return pipeline.build_resume_context(
        resume_id=resume.resume_id,
        text=resume.text,
        skills=resume.skills,
        preferred_locations=resume.preferred_locations,
        max_experience_years=resume.max_experience_years,
    )
