"""Supplemental Phase-8 coverage: Mongo cache, hybrid/error paths, ST non-torch."""

from __future__ import annotations

import pytest
from app.ai.metrics import AiMetricsService
from app.ai.search import VectorSearchService
from app.embeddings.cache import MongoEmbeddingCache, content_key
from app.embeddings.factory import build_embedding_provider
from app.embeddings.hashing import HashingEmbeddingProvider
from app.embeddings.sentence_transformer import (
    EmbeddingModelUnavailable,
    SentenceTransformerProvider,
)
from app.metrics.memory import InMemoryMetrics
from app.vector.numpy_scorer import NumpyCosineScorer

# The three ``*_without_model`` tests describe behaviour when the ``ml`` extra is
# absent. When it is installed (real BAAI/bge-small-en-v1.5 available), skip them.
_skip_if_ml = pytest.mark.skipif(
    SentenceTransformerProvider.available(),
    reason="ml extra installed — absence-path behaviour not exercised",
)


# ---- Mongo embedding cache --------------------------------------------------
async def test_mongo_embedding_cache_roundtrip(mock_db) -> None:
    cache = MongoEmbeddingCache(mock_db)
    k1, k2 = content_key("m", "a"), content_key("m", "b")
    await cache.set_many({k1: [1.0, 2.0], k2: [3.0, 4.0]})
    assert await cache.get(k1) == [1.0, 2.0]
    many = await cache.get_many([k1, k2, "missing"])
    assert set(many) == {k1, k2}
    stats = await cache.stats()
    assert stats.backend == "mongo" and stats.size == 2
    assert stats.hits >= 2 and stats.misses >= 1


async def test_mongo_cache_get_missing(mock_db) -> None:
    cache = MongoEmbeddingCache(mock_db)
    assert await cache.get("nope") is None


# ---- vector search: hybrid + query_vector + no hydrate ----------------------
class _HybridScorer(NumpyCosineScorer):
    async def hybrid_search(self, query_vector, text, *, limit, alpha, filters, score_threshold):  # type: ignore[no-untyped-def]
        return await self.search(query_vector, limit=limit)


async def test_vector_search_hybrid_and_query_vector(mock_db) -> None:
    from app.db.repositories.jobs import JobRepository

    repo = JobRepository(mock_db)
    scorer = _HybridScorer([("h1", [1.0, 0.0]), ("h2", [0.0, 1.0])])
    service = VectorSearchService(HashingEmbeddingProvider(dimensions=2), scorer, repo)

    hybrid = await service.search(text="anything", query_vector=[1.0, 0.0], limit=2, hybrid=True)
    assert hybrid.total >= 1

    # explicit query_vector + no hydration (jobs not in repo → job stays None)
    plain = await service.search(query_vector=[1.0, 0.0], limit=1, hydrate=False)
    assert plain.hits and plain.hits[0].job is None


# ---- ai metrics with no cache / no embedder ---------------------------------
async def test_ai_metrics_minimal() -> None:
    report = await AiMetricsService(InMemoryMetrics()).build()
    assert report.cache.backend == "none"
    assert report.device == {"device": "cpu"}


# ---- sentence-transformer non-torch paths -----------------------------------
def test_st_from_settings_and_device_info() -> None:
    from app.ai.registry import ModelRegistry
    from app.config.settings import EmbeddingSettings

    registry = ModelRegistry()
    provider = SentenceTransformerProvider.from_settings(
        EmbeddingSettings(), dimensions=384, registry=registry, metrics=InMemoryMetrics()
    )
    assert provider.model_name == "BAAI/bge-small-en-v1.5"
    # registry learned about the model
    assert registry.active() is not None
    info = provider.device_info()
    assert info["device"] == "cpu" and info["cuda_available"] is False


@_skip_if_ml
def test_st_embed_query_raises_without_model() -> None:
    provider = SentenceTransformerProvider(dimensions=384)
    try:
        provider.embed_query("hi")
        raise AssertionError("expected EmbeddingModelUnavailable")
    except EmbeddingModelUnavailable:
        pass


@_skip_if_ml
async def test_st_health_check_false_without_model() -> None:
    from app.ai.registry import ModelRegistry

    registry = ModelRegistry()
    provider = SentenceTransformerProvider(dimensions=384, registry=registry)
    assert await provider.health_check() is False


@_skip_if_ml
async def test_st_warmup_propagates_without_model() -> None:
    provider = SentenceTransformerProvider(dimensions=384)
    try:
        await provider.warmup()
        raise AssertionError("expected EmbeddingModelUnavailable")
    except EmbeddingModelUnavailable:
        pass


# ---- atlas scorer: error + hybrid-no-text + normalise-equal -----------------
class _BoomCollection:
    def aggregate(self, pipeline):  # type: ignore[no-untyped-def]
        raise RuntimeError("no atlas here")


async def test_atlas_search_error_returns_empty() -> None:
    from app.vector.atlas_scorer import AtlasVectorScorer

    scorer = AtlasVectorScorer(_BoomCollection(), index_name="i")  # type: ignore[arg-type]
    assert await scorer.search([0.1], limit=3) == []


async def test_atlas_hybrid_no_text_is_pure_semantic() -> None:
    from app.vector.atlas_scorer import AtlasVectorScorer

    from tests.unit.test_ai_vector import _FakeCollection

    col = _FakeCollection([{"job_id": "h1", "score": 0.9}, {"job_id": "h1", "score": 0.9}])
    scorer = AtlasVectorScorer(col, index_name="i")  # type: ignore[arg-type]
    hits = await scorer.hybrid_search([0.1], "   ", limit=1, alpha=0.6)
    assert hits and hits[0].job_id == "h1"


# ---- factory builds its own cache when none is passed -----------------------
def test_factory_builds_internal_cache() -> None:
    from app.config.settings import EmbeddingCacheBackend, EmbeddingProviderType, Settings
    from app.embeddings.cached import CachedEmbeddingProvider

    settings = Settings(
        embedding={  # type: ignore[arg-type]
            "provider": EmbeddingProviderType.HASHING,
            "cache_backend": EmbeddingCacheBackend.MEMORY,
        }
    )
    provider = build_embedding_provider(settings)  # no cache passed → built internally
    assert isinstance(provider, CachedEmbeddingProvider)


# ---- cached provider properties + warmup ------------------------------------
async def test_cached_provider_properties_and_warmup() -> None:
    from app.embeddings.cache import MemoryEmbeddingCache
    from app.embeddings.cached import CachedEmbeddingProvider

    base = HashingEmbeddingProvider(dimensions=8)
    cache = MemoryEmbeddingCache()
    provider = CachedEmbeddingProvider(base, cache)
    assert provider.delegate is base
    assert provider.cache is cache
    assert provider.embed_documents(["x"])  # sync pass-through
    assert provider.embed_query("x")
    await provider.warmup()  # delegates to no-op
    assert await provider.health_check() is True


# ---- ai metrics: device_info that raises ------------------------------------
async def test_ai_metrics_device_info_exception() -> None:
    class _BadDevice(HashingEmbeddingProvider):
        def device_info(self) -> dict[str, object]:
            raise RuntimeError("boom")

    report = await AiMetricsService(InMemoryMetrics(), embedder=_BadDevice(dimensions=8)).build()
    assert report.device == {"device": "unknown"}


# ---- job service edges ------------------------------------------------------
async def test_job_service_empty_and_no_repo() -> None:
    from app.ai.job_service import JobEmbeddingService

    service = JobEmbeddingService(HashingEmbeddingProvider(dimensions=8))
    empty = await service.embed_jobs([])
    assert empty.total == 0 and empty.embedded == 0
    # no repo configured → embed_stored is a no-op
    stats = await service.embed_stored()
    assert stats.embedded == 0


async def test_job_service_embed_stored_force(mock_db) -> None:
    from app.ai.job_service import JobEmbeddingService
    from app.db.repositories.jobs import JobRepository

    repo = JobRepository(mock_db)
    for i in range(2):
        await repo.upsert_by_hash(_cov_job(i))
    service = JobEmbeddingService(HashingEmbeddingProvider(dimensions=8), jobs=repo)
    # force + not only_missing → re-embeds everything
    stats = await service.embed_stored(force=True, only_missing=False)
    assert stats.embedded == 2 and stats.persisted == 2


def _cov_job(i: int):  # type: ignore[no-untyped-def]
    from app.models.common import Location
    from app.models.job import Job

    return Job(
        job_hash=f"c{i}", external_id=str(i), source="s", company_name="Acme",
        role="Engineer", url=f"https://x/{i}", location=Location(city="Pune"),
        description="python engineer",
    )
