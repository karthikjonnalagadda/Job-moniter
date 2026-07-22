"""Job embedding service — embed once, skip unchanged, and migrate on demand.

Embeds jobs and stamps ``embedding_meta`` (model / version / content hash /
timestamp). A job is re-embedded only when its content hash, model, or embedding
version differs from what is stored — so new jobs cost one inference each and
untouched jobs cost nothing (the job half of incremental embedding).

``EmbeddingMigrator`` re-embeds stored jobs when the model changes (e.g.
bge-small → bge-base) so a model upgrade is a background pass, not a rebuild.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import Field

from app.ai.resume_service import text_hash
from app.config.logging import get_logger
from app.core.normalization.engine import job_text
from app.models.base import AppBaseModel
from app.models.common import DEFAULT_USER_ID, EMBEDDING_VERSION, EmbeddingMeta

if TYPE_CHECKING:
    from app.db.repositories.jobs import JobRepository
    from app.embeddings.provider import EmbeddingProvider
    from app.metrics.base import MetricsSink
    from app.models.job import Job

log = get_logger("rank")


class EmbeddingStats(AppBaseModel):
    """Result of an embedding pass."""

    total: int = 0
    embedded: int = 0
    skipped: int = 0
    persisted: int = 0
    took_ms: float = 0.0
    model_name: str = ""
    errors: list[str] = Field(default_factory=list)


class JobEmbeddingService:
    """Compute + attach embeddings to jobs, incrementally."""

    def __init__(
        self,
        embedder: EmbeddingProvider,
        *,
        jobs: JobRepository | None = None,
        metrics: MetricsSink | None = None,
    ) -> None:
        self._embedder = embedder
        self._jobs = jobs
        self._metrics = metrics

    def _current_hash(self, job: Job) -> str:
        return text_hash(job_text(job))

    def _is_fresh(self, job: Job, digest: str) -> bool:
        meta = job.embedding_meta
        return bool(
            job.embedding
            and meta is not None
            and meta.content_hash == digest
            and meta.model_name == self._embedder.model_name
            and meta.embedding_version == EMBEDDING_VERSION
        )

    async def embed_jobs(self, jobs: list[Job], *, force: bool = False) -> EmbeddingStats:
        """Attach embeddings to ``jobs`` in place; skip those already up to date."""

        import time

        started = time.perf_counter()
        stats = EmbeddingStats(total=len(jobs), model_name=self._embedder.model_name)

        pending: list[tuple[Job, str]] = []
        for job in jobs:
            digest = self._current_hash(job)
            if not force and self._is_fresh(job, digest):
                stats.skipped += 1
                continue
            pending.append((job, digest))

        if pending:
            vectors = await self._embedder.aembed_documents([job_text(j) for j, _ in pending])
            now = datetime.now(tz=UTC)
            for (job, digest), vector in zip(pending, vectors, strict=True):
                job.embedding = vector
                job.embedding_meta = EmbeddingMeta(
                    model_name=self._embedder.model_name,
                    embedding_version=EMBEDDING_VERSION,
                    dimensions=len(vector),
                    content_hash=digest,
                    generated_at=now,
                )
                stats.embedded += 1

        stats.took_ms = round((time.perf_counter() - started) * 1000.0, 3)
        if self._metrics is not None and stats.embedded:
            self._metrics.observe("ai_embed_job_batch_seconds", stats.took_ms / 1000.0)
        return stats

    async def embed_stored(
        self,
        *,
        user_id: str = DEFAULT_USER_ID,
        limit: int = 100_000,
        force: bool = False,
        only_missing: bool = True,
    ) -> EmbeddingStats:
        """Embed jobs already in the repository and persist the vectors."""

        if self._jobs is None:
            return EmbeddingStats(model_name=self._embedder.model_name)
        if only_missing and not force:
            jobs = await self._jobs.iter_missing_embeddings(user_id=user_id, limit=limit)
        else:
            jobs = await self._jobs.find({"user_id": user_id}, limit=limit)
        stats = await self.embed_jobs(jobs, force=force)
        for job in jobs:
            if job.embedding is not None:
                await self._jobs.upsert_by_hash(job)
                stats.persisted += 1
        return stats


class MigrationReport(AppBaseModel):
    """Outcome of an embedding model migration."""

    scanned: int = 0
    migrated: int = 0
    from_models: dict[str, int] = Field(default_factory=dict)
    to_model: str = ""
    took_ms: float = 0.0


class EmbeddingMigrator:
    """Re-embed stored jobs onto the current model (for model upgrades)."""

    def __init__(self, service: JobEmbeddingService, jobs: JobRepository) -> None:
        self._service = service
        self._jobs = jobs

    async def migrate(
        self, *, user_id: str = DEFAULT_USER_ID, limit: int = 100_000
    ) -> MigrationReport:
        import time

        started = time.perf_counter()
        stored = await self._jobs.find({"user_id": user_id}, limit=limit)
        report = MigrationReport(
            scanned=len(stored), to_model=self._service._embedder.model_name
        )
        stale: list[Job] = []
        for job in stored:
            meta = job.embedding_meta
            source = meta.model_name if meta else "none"
            if source != report.to_model or job.embedding is None:
                report.from_models[source] = report.from_models.get(source, 0) + 1
                stale.append(job)
        if stale:
            await self._service.embed_jobs(stale, force=True)
            for job in stale:
                await self._jobs.upsert_by_hash(job)
            report.migrated = len(stale)
        report.took_ms = round((time.perf_counter() - started) * 1000.0, 3)
        return report
