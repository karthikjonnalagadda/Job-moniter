"""Job processing pipeline orchestrator.

Runs the end-to-end flow with per-stage benchmarking:

    validate → normalize → filter → deduplicate → embed → rank → quality → store

Each stage takes an explicit input and returns an explicit output (no shared
mutable state), so stages are independently testable and benchmarkable, and the
funnel counts are recorded on a ``PipelineRun``. Supports single/batch input,
resume-aware ranking, incremental de-dup against stored jobs, and resume-only
re-ranking (``rerank``) without re-fetching postings.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import Field

from app.collectors.base import RawJob
from app.config.logging import get_logger
from app.core.dedup.detector import DedupResult, DuplicateDetector
from app.core.normalization.engine import job_text
from app.core.ranking.engine import RankingEngine, ResumeContext
from app.core.skills.extractor import ExtractedSkills
from app.models.base import AppBaseModel
from app.models.common import DEFAULT_USER_ID
from app.models.enums import ATSType, RunStatus, SourceType
from app.models.job import Job
from app.models.pipeline_run import PipelineRun, StageStat

if TYPE_CHECKING:
    from app.core.filters.chain import FilterChain
    from app.core.normalization.engine import NormalizationEngine
    from app.core.quality import QualityScorer
    from app.db.repositories.jobs import JobRepository
    from app.db.repositories.pipeline_runs import PipelineRunRepository
    from app.embeddings.provider import EmbeddingProvider
    from app.importers.aliases import AliasResolver

log = get_logger("pipeline")


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class ProcessItem(AppBaseModel):
    """One collected posting plus the provenance the normaliser needs."""

    raw: RawJob
    source: str
    source_type: SourceType = SourceType.ATS
    ats_type: ATSType = ATSType.UNKNOWN
    collector_version: str | None = None
    career_url: str | None = None
    collector_confidence: float = 1.0


class PipelineResult(AppBaseModel):
    """Outcome of a processing run."""

    run: PipelineRun
    jobs: list[Job] = Field(default_factory=list)
    dedup: DedupResult | None = None


class JobProcessingPipeline:
    """Orchestrates normalise → filter → dedup → embed → rank → store."""

    def __init__(
        self,
        *,
        normalizer: NormalizationEngine,
        filter_chain: FilterChain,
        embedder: EmbeddingProvider,
        ranker: RankingEngine,
        quality: QualityScorer,
        aliases: AliasResolver | None = None,
        jobs: JobRepository | None = None,
        runs: PipelineRunRepository | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._normalizer = normalizer
        self._filters = filter_chain
        self._embedder = embedder
        self._ranker = ranker
        self._quality = quality
        self._aliases = aliases
        self._jobs = jobs
        self._runs = runs
        self._now = now or _utcnow
        self._last_rejected: dict[str, int] = {}

    # ---- public API -----------------------------------------------------
    async def process(
        self,
        items: list[ProcessItem],
        *,
        resume: ResumeContext | None = None,
        company_priority: dict[str, float] | None = None,
        persist: bool = True,
        incremental: bool = False,
        user_id: str = DEFAULT_USER_ID,
        correlation_id: str | None = None,
    ) -> PipelineResult:
        run = PipelineRun(
            run_id=uuid.uuid4().hex,
            user_id=user_id,
            resume_id=resume.resume_id if resume else None,
            correlation_id=correlation_id,
            started_at=self._now(),
            collected=len(items),
        )
        started = time.perf_counter()

        valid = self._stage(run, "validate", items, self._validate)
        run.validated = len(valid)

        normalized = self._stage(
            run, "normalize", valid, lambda xs: self._normalize(xs, user_id, correlation_id)
        )
        run.normalized = len(normalized)

        kept = self._stage(run, "filter", normalized, self._filter)
        run.filtered_out = len(normalized) - len(kept)

        unique, dedup = await self._dedup_stage(run, kept, incremental=incremental)
        run.duplicates = dedup.duplicates

        embedded = self._stage(run, "embed", unique, self._embed)

        ranked = self._stage(
            run, "rank", embedded, lambda xs: self._rank(xs, resume, company_priority)
        )
        run.ranked = sum(1 for j in ranked if j.match is not None)

        stored = await self._store_stage(run, ranked) if persist else ranked
        run.stored = len(stored) if persist else 0

        run.finished_at = self._now()
        run.duration_seconds = round(time.perf_counter() - started, 4)
        run.status = RunStatus.SUCCESS
        run.rejected_by = self._last_rejected
        if persist:  # run history is a persistence concern — skip when not storing
            await self._save_run(run)
        log.info(
            "Pipeline {}: {} in → {} stored ({} filtered, {} dup)",
            run.run_id,
            run.collected,
            run.stored,
            run.filtered_out,
            run.duplicates,
        )
        return PipelineResult(run=run, jobs=ranked, dedup=dedup)

    def deduplicate(self, jobs: list[Job]) -> tuple[list[Job], DedupResult]:
        """Standalone de-duplication of already-normalised jobs."""

        return DuplicateDetector(aliases=self._aliases).deduplicate(jobs)

    def extract_skills(self, *texts: str) -> ExtractedSkills:
        """Standalone skill extraction (used by the extract-skills endpoint)."""

        return self._normalizer.skills.extract(*texts)

    def build_resume_context(
        self,
        *,
        resume_id: str | None = None,
        text: str | None = None,
        skills: list[str] | None = None,
        preferred_locations: list[str] | None = None,
        max_experience_years: float = 2.0,
    ) -> ResumeContext:
        """Build a ``ResumeContext`` (embedding + skills) from raw resume input."""

        merged = list(skills or [])
        if text:
            extracted = self._normalizer.skills.extract(text)
            for skill in extracted.skills:
                if skill not in merged:
                    merged.append(skill)
        query = " ".join(filter(None, [text or "", " ".join(merged)])).strip()
        embedding = self._embedder.embed_query(query) if query else None
        return ResumeContext(
            resume_id=resume_id,
            embedding=embedding,
            skills=merged,
            preferred_locations=list(preferred_locations or []),
            max_experience_years=max_experience_years,
        )

    def rank_jobs(
        self,
        jobs: list[Job],
        resume: ResumeContext,
        *,
        company_priority: dict[str, float] | None = None,
    ) -> list[Job]:
        """Rank a provided set of jobs against a resume (no fetch, no store)."""

        return self._rank(self._embed(jobs), resume, company_priority)

    async def rerank(
        self,
        resume: ResumeContext,
        *,
        user_id: str = DEFAULT_USER_ID,
        limit: int = 1000,
        persist: bool = True,
    ) -> list[Job]:
        """Re-rank stored jobs for a (new) resume without re-fetching postings."""

        if self._jobs is None:
            return []
        stored = await self._jobs.find({"user_id": user_id}, limit=limit)
        ranked = self._rank(self._embed(stored), resume, None)
        if persist:
            for job in ranked:
                await self._jobs.upsert_by_hash(job)
        return ranked

    # ---- stages ---------------------------------------------------------
    def _validate(self, items: list[ProcessItem]) -> list[ProcessItem]:
        return [
            it for it in items if it.raw.external_id and it.raw.title and it.raw.url
        ]

    def _normalize(
        self, items: list[ProcessItem], user_id: str, correlation_id: str | None
    ) -> list[Job]:
        out: list[Job] = []
        for item in items:
            job = self._normalizer.normalize(
                item.raw,
                source=item.source,
                source_type=item.source_type,
                ats_type=item.ats_type,
                collector_version=item.collector_version,
                career_url=item.career_url,
                collector_confidence=item.collector_confidence,
                user_id=user_id,
                correlation_id=correlation_id,
            )
            out.append(job)
        return out

    def _filter(self, jobs: list[Job]) -> list[Job]:
        kept, summary = self._filters.apply(jobs)
        self._last_rejected = summary.rejected_by
        return kept

    async def _dedup_stage(
        self, run: PipelineRun, jobs: list[Job], *, incremental: bool
    ) -> tuple[list[Job], DedupResult]:
        started = time.perf_counter()
        detector = DuplicateDetector(aliases=self._aliases)
        unique, result = detector.deduplicate(jobs)
        if incremental and self._jobs is not None:
            filtered: list[Job] = []
            skipped = 0
            for job in unique:
                if await self._jobs.exists_hash(job.job_hash):
                    skipped += 1
                    continue
                filtered.append(job)
            result = DedupResult(
                unique=len(filtered),
                duplicates=result.duplicates + skipped,
                verdicts=result.verdicts,
            )
            unique = filtered
        run.stages.append(
            StageStat(
                name="deduplicate",
                count_in=len(jobs),
                count_out=len(unique),
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
            )
        )
        return unique, result

    def _embed(self, jobs: list[Job]) -> list[Job]:
        if not jobs:
            return jobs
        vectors = self._embedder.embed_documents([job_text(j) for j in jobs])
        for job, vector in zip(jobs, vectors, strict=True):
            job.embedding = vector
        return jobs

    def _rank(
        self,
        jobs: list[Job],
        resume: ResumeContext | None,
        company_priority: dict[str, float] | None,
    ) -> list[Job]:
        if resume is None:
            return jobs
        priority = company_priority or {}
        for job in jobs:
            key = (job.canonical_company_name or job.company_name).lower()
            job.match = self._ranker.rank(
                job, resume, company_priority=priority.get(key, 0.5)
            )
        jobs.sort(key=lambda j: j.match.score if j.match else 0.0, reverse=True)
        return jobs

    async def _store_stage(self, run: PipelineRun, jobs: list[Job]) -> list[Job]:
        if self._jobs is None:
            return []
        started = time.perf_counter()
        stored: list[Job] = []
        for job in jobs:
            stored.append(await self._jobs.upsert_by_hash(job))
        run.stages.append(
            StageStat(
                name="store",
                count_in=len(jobs),
                count_out=len(stored),
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
            )
        )
        return stored

    # ---- helpers --------------------------------------------------------
    def _stage(
        self,
        run: PipelineRun,
        name: str,
        payload: list[Any],
        fn: Callable[[list[Any]], list[Any]],
    ) -> list[Any]:
        started = time.perf_counter()
        result = fn(payload)
        run.stages.append(
            StageStat(
                name=name,
                count_in=len(payload),
                count_out=len(result),
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
            )
        )
        return result

    async def _save_run(self, run: PipelineRun) -> None:
        if self._runs is not None:
            await self._runs.insert(run)
