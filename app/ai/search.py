"""Vector search service — text/resume → ranked jobs.

Ties the embedding provider to a ``VectorScorer`` and the job repository:

    query text ─▶ embed_query ─▶ VectorScorer.search ─▶ fetch jobs ─▶ page

Backend-agnostic: works with ``AtlasVectorScorer`` (production ``$vectorSearch``)
or ``NumpyCosineScorer`` (dev/CI) through the ``VectorScorer`` port. Supports
metadata filters, a score threshold, pagination, and an optional hybrid
(semantic + lexical) mode when the scorer provides it.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from pydantic import Field

from app.models.base import AppBaseModel
from app.models.job import Job  # runtime import: referenced by the SearchHit schema

if TYPE_CHECKING:
    from app.db.repositories.jobs import JobRepository
    from app.embeddings.provider import EmbeddingProvider
    from app.metrics.base import MetricsSink
    from app.vector.scorer import VectorScorer


class SearchHit(AppBaseModel):
    """One search result: the job plus its semantic score."""

    job_id: str
    score: float
    job: Job | None = None


class SearchResults(AppBaseModel):
    """A page of vector-search results."""

    query: str = ""
    total: int = 0  # hits on this page
    limit: int = 20
    skip: int = 0
    took_ms: float = 0.0
    hits: list[SearchHit] = Field(default_factory=list)


class VectorSearchService:
    """Semantic job search over the configured vector backend."""

    def __init__(
        self,
        embedder: EmbeddingProvider,
        scorer: VectorScorer,
        jobs: JobRepository,
        *,
        metrics: MetricsSink | None = None,
    ) -> None:
        self._embedder = embedder
        self._scorer = scorer
        self._jobs = jobs
        self._metrics = metrics

    async def search(
        self,
        *,
        text: str | None = None,
        query_vector: list[float] | None = None,
        limit: int = 20,
        skip: int = 0,
        filters: dict[str, object] | None = None,
        score_threshold: float = 0.0,
        hybrid: bool = False,
        hybrid_alpha: float = 0.6,
        hydrate: bool = True,
    ) -> SearchResults:
        """Run a semantic (or hybrid) search and return a page of hits."""

        started = time.perf_counter()
        if query_vector is None:
            query_vector = await self._embedder.aembed_query(text or "")

        scored = await self._run_scorer(
            query_vector,
            text=text or "",
            limit=limit,
            skip=skip,
            filters=filters,
            score_threshold=score_threshold,
            hybrid=hybrid,
            hybrid_alpha=hybrid_alpha,
        )

        hits = [SearchHit(job_id=s.job_id, score=round(s.similarity, 4)) for s in scored]
        if hydrate and hits:
            by_hash = await self._jobs.find_by_hashes([h.job_id for h in hits])
            for hit in hits:
                hit.job = by_hash.get(hit.job_id)

        took_ms = (time.perf_counter() - started) * 1000.0
        if self._metrics is not None:
            self._metrics.observe("ai_vector_search_seconds", took_ms / 1000.0)
        return SearchResults(
            query=text or "",
            total=len(hits),
            limit=limit,
            skip=skip,
            took_ms=round(took_ms, 3),
            hits=hits,
        )

    async def _run_scorer(
        self,
        query_vector: list[float],
        *,
        text: str,
        limit: int,
        skip: int,
        filters: dict[str, object] | None,
        score_threshold: float,
        hybrid: bool,
        hybrid_alpha: float,
    ) -> list:
        if hybrid and hasattr(self._scorer, "hybrid_search"):
            return await self._scorer.hybrid_search(
                query_vector,
                text,
                limit=limit,
                alpha=hybrid_alpha,
                filters=filters,
                score_threshold=score_threshold,
            )
        return await self._scorer.search(
            query_vector,
            limit=limit,
            filters=filters,
            score_threshold=score_threshold,
            skip=skip,
        )
