"""Vector scoring port.

Two interchangeable backends implement this (Phase 9):
    * ``AtlasVectorScorer`` — production default; runs ``$vectorSearch`` against
      the Atlas index on ``jobs.embedding``.
    * ``NumpyCosineScorer`` — local dev / unit tests; pure numpy cosine, no infra.

Selected by ``settings.vector.backend``. The ranking engine depends only on this
interface, so the two are fully interchangeable (Liskov / Dependency Inversion).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.models.base import AppBaseModel


class ScoredJob(AppBaseModel):
    """A job id with its raw semantic similarity in [0, 1]."""

    job_id: str
    similarity: float


class VectorScorer(ABC):
    """Abstraction over 'rank jobs by similarity to a query vector'."""

    @abstractmethod
    async def search(
        self,
        query_vector: Sequence[float],
        *,
        limit: int,
        filters: dict[str, object] | None = None,
        score_threshold: float = 0.0,
        skip: int = 0,
    ) -> list[ScoredJob]:
        """Return the top ``limit`` jobs most similar to ``query_vector``.

        ``score_threshold`` drops results below that cosine score; ``skip``
        offsets into the ranked list for pagination. Both backends honour them
        so callers stay backend-agnostic.
        """
