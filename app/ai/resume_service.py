"""Resume embedding service — embed once per version, skip when unchanged.

Generates and stores an embedding for each resume version (Backend / AI / QA /
Data …). Regeneration is gated on an embedding *diff*: if the resume text, the
model, and the embedding version are all unchanged, the stored vector is reused
(``regenerated=False``). This is the resume half of incremental embedding.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.ai.registry import ModelRegistry
from app.config.logging import get_logger
from app.core.ranking.engine import ResumeContext
from app.models.common import DEFAULT_USER_ID, EMBEDDING_VERSION
from app.models.resume import ResumeEmbedding

if TYPE_CHECKING:
    from app.db.repositories.resume_embeddings import ResumeEmbeddingRepository
    from app.embeddings.provider import EmbeddingProvider

log = get_logger("rank")


def text_hash(text: str) -> str:
    """Model-independent sha256 of resume text (change detection)."""

    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class ResumeEmbeddingResult:
    """Outcome of an embed request."""

    def __init__(self, resume: ResumeEmbedding, *, regenerated: bool) -> None:
        self.resume = resume
        self.regenerated = regenerated


class ResumeEmbeddingService:
    """Create/refresh resume-version embeddings with diff detection."""

    def __init__(
        self,
        embedder: EmbeddingProvider,
        repo: ResumeEmbeddingRepository,
        *,
        registry: ModelRegistry | None = None,
    ) -> None:
        self._embedder = embedder
        self._repo = repo
        self._registry = registry

    async def is_changed(
        self, resume_id: str, content: str, *, user_id: str = DEFAULT_USER_ID
    ) -> bool:
        """True if embedding ``content`` for ``resume_id`` would change the vector."""

        existing = await self._repo.get_by_resume_id(resume_id, user_id=user_id)
        return self._needs_regen(existing, text_hash(content))

    async def embed_resume(
        self,
        resume_id: str,
        content: str,
        *,
        label: str | None = None,
        skills: list[str] | None = None,
        preferred_locations: list[str] | None = None,
        max_experience_years: float = 2.0,
        user_id: str = DEFAULT_USER_ID,
        force: bool = False,
    ) -> ResumeEmbeddingResult:
        digest = text_hash(content)
        existing = await self._repo.get_by_resume_id(resume_id, user_id=user_id)
        if not force and not self._needs_regen(existing, digest) and existing is not None:
            log.debug("Resume '{}' unchanged — reusing embedding", resume_id)
            return ResumeEmbeddingResult(existing, regenerated=False)

        vector = await self._embedder.aembed_query(content)
        record = ResumeEmbedding(
            resume_id=resume_id,
            label=label or (existing.label if existing else None),
            user_id=user_id,
            content_hash=digest,
            embedding=vector,
            dimensions=len(vector),
            model_name=self._embedder.model_name,
            embedding_version=EMBEDDING_VERSION,
            generated_at=datetime.now(tz=UTC),
            skills=skills or (existing.skills if existing else []),
            preferred_locations=preferred_locations
            or (existing.preferred_locations if existing else []),
            max_experience_years=max_experience_years,
        )
        stored = await self._repo.upsert_resume(record)
        log.info(
            "Embedded resume '{}' ({} dims, model={})",
            resume_id,
            len(vector),
            self._embedder.model_name,
        )
        return ResumeEmbeddingResult(stored, regenerated=True)

    def to_context(self, resume: ResumeEmbedding) -> ResumeContext:
        """Convert a stored resume embedding into a ranking ``ResumeContext``."""

        return ResumeContext(
            resume_id=resume.resume_id,
            embedding=resume.embedding or None,
            skills=list(resume.skills),
            preferred_locations=list(resume.preferred_locations),
            max_experience_years=resume.max_experience_years,
        )

    def _needs_regen(self, existing: ResumeEmbedding | None, digest: str) -> bool:
        if existing is None:
            return True
        return (
            existing.content_hash != digest
            or existing.model_name != self._embedder.model_name
            or existing.embedding_version != EMBEDDING_VERSION
            or not existing.embedding
        )
