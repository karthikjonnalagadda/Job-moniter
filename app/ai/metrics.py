"""AI metrics — a consolidated view of the AI layer's runtime behaviour.

Reads the shared ``MetricsSink`` (latency summaries recorded by the embedding
provider, vector search, and reranker), the embedding cache stats (hit/miss
rate), the model registry (loaded/health/latency/memory), and the compute-device
report. Served by ``GET /ai/metrics``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from app.ai.registry import ModelRecord
from app.models.base import AppBaseModel

if TYPE_CHECKING:
    from app.ai.registry import ModelRegistry
    from app.embeddings.cache import EmbeddingCache
    from app.embeddings.provider import EmbeddingProvider
    from app.metrics.base import MetricsSink

# Metric names recorded across the AI layer (seconds; summary → average).
_EMBED_QUERY = "ai_embed_query_seconds"
_EMBED_DOCS = "ai_embed_documents_seconds"
_EMBED_BATCH = "ai_embed_job_batch_seconds"
_VECTOR_SEARCH = "ai_vector_search_seconds"
_RERANK = "ai_rerank_seconds"
_RANK = "ai_rank_seconds"


class CacheMetrics(AppBaseModel):
    backend: str = "none"
    hits: int = 0
    misses: int = 0
    hit_rate: float = 0.0
    size: int = 0


class AiMetricsReport(AppBaseModel):
    """Point-in-time AI metrics snapshot."""

    embed_query_ms: float = 0.0
    embed_documents_ms: float = 0.0
    embed_batch_ms: float = 0.0
    vector_search_ms: float = 0.0
    rerank_ms: float = 0.0
    ranking_ms: float = 0.0
    cache: CacheMetrics = Field(default_factory=CacheMetrics)
    models: list[ModelRecord] = Field(default_factory=list)
    device: dict[str, object] = Field(default_factory=dict)


class AiMetricsService:
    """Assemble an :class:`AiMetricsReport` from the AI runtime state."""

    def __init__(
        self,
        metrics: MetricsSink,
        *,
        cache: EmbeddingCache | None = None,
        registry: ModelRegistry | None = None,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self._metrics = metrics
        self._cache = cache
        self._registry = registry
        self._embedder = embedder

    async def build(self) -> AiMetricsReport:
        averages = self._metrics.snapshot().averages()

        def ms(name: str) -> float:
            return round(averages.get(name, 0.0) * 1000.0, 3)

        report = AiMetricsReport(
            embed_query_ms=ms(_EMBED_QUERY),
            embed_documents_ms=ms(_EMBED_DOCS),
            embed_batch_ms=ms(_EMBED_BATCH),
            vector_search_ms=ms(_VECTOR_SEARCH),
            rerank_ms=ms(_RERANK),
            ranking_ms=ms(_RANK),
        )
        if self._cache is not None:
            stats = await self._cache.stats()
            report.cache = CacheMetrics(
                backend=stats.backend,
                hits=stats.hits,
                misses=stats.misses,
                hit_rate=stats.hit_rate,
                size=stats.size,
            )
        if self._registry is not None:
            report.models = self._registry.list()
        report.device = self._device_info()
        return report

    def _device_info(self) -> dict[str, object]:
        info = getattr(self._embedder, "device_info", None)
        if callable(info):
            try:
                result: dict[str, object] = info()
                return result
            except Exception:
                return {"device": "unknown"}
        return {"device": "cpu"}
