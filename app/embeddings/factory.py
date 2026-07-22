"""Embedding provider + cache factories.

Selects the concrete ``EmbeddingProvider`` from settings and wraps it in a cache:

    provider = auto   →  sentence-transformers if importable, else hashing
             = sentence_transformer → force the model (fallback to hashing if
               ``fallback_to_hashing`` and the ``ml`` extra is absent)
             = hashing → force the deterministic encoder (CI/dev default)

The production model plugs in behind the same ``EmbeddingProvider`` port, so no
caller changes. Graceful fallback means a missing ``ml`` extra never breaks boot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config.logging import get_logger
from app.config.settings import EmbeddingCacheBackend, EmbeddingProviderType
from app.embeddings.cache import (
    EmbeddingCache,
    MemoryEmbeddingCache,
    MongoEmbeddingCache,
    NullEmbeddingCache,
)
from app.embeddings.cached import CachedEmbeddingProvider
from app.embeddings.hashing import HashingEmbeddingProvider
from app.embeddings.provider import EmbeddingProvider

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

    from app.ai.registry import ModelRegistry
    from app.config.settings import Settings
    from app.metrics.base import MetricsSink

log = get_logger("rank")


def _build_hashing(settings: Settings, registry: ModelRegistry | None) -> EmbeddingProvider:
    provider = HashingEmbeddingProvider(
        dimensions=settings.vector.dimensions,
        query_instruction=settings.embedding.query_instruction,
    )
    if registry is not None:
        registry.register_name("hashing", dimensions=provider.dimensions, active=True)
        registry.set_loaded("hashing", loaded=True)
        registry.set_health("hashing", healthy=True)
    return provider


def _build_sentence_transformer(
    settings: Settings,
    registry: ModelRegistry | None,
    metrics: MetricsSink | None,
) -> EmbeddingProvider:
    from app.embeddings.sentence_transformer import SentenceTransformerProvider

    return SentenceTransformerProvider.from_settings(
        settings.embedding,
        dimensions=settings.vector.dimensions,
        registry=registry,
        metrics=metrics,
    )


def build_base_embedding_provider(
    settings: Settings,
    *,
    registry: ModelRegistry | None = None,
    metrics: MetricsSink | None = None,
) -> EmbeddingProvider:
    """Return the configured provider *without* the cache wrapper."""

    kind = settings.embedding.provider
    from app.embeddings.sentence_transformer import SentenceTransformerProvider

    if kind is EmbeddingProviderType.HASHING:
        log.debug("Embedding provider: hashing (forced)")
        return _build_hashing(settings, registry)

    st_available = SentenceTransformerProvider.available()

    if kind is EmbeddingProviderType.SENTENCE_TRANSFORMER:
        if st_available:
            log.info("Embedding provider: sentence-transformers ({})", settings.embedding.model_name)  # noqa: E501
            return _build_sentence_transformer(settings, registry, metrics)
        if settings.embedding.fallback_to_hashing:
            log.warning(
                "sentence-transformers not installed — falling back to hashing encoder"
            )
            return _build_hashing(settings, registry)
        from app.embeddings.sentence_transformer import EmbeddingModelUnavailable

        raise EmbeddingModelUnavailable(
            "sentence-transformers required but not installed and fallback disabled"
        )

    # AUTO
    if st_available:
        log.info("Embedding provider: sentence-transformers (auto, {})", settings.embedding.model_name)  # noqa: E501
        return _build_sentence_transformer(settings, registry, metrics)
    log.info("Embedding provider: hashing (auto — ml extra not installed)")
    return _build_hashing(settings, registry)


def build_embedding_cache(
    settings: Settings, *, db: AsyncIOMotorDatabase | None = None
) -> EmbeddingCache:
    """Build the embedding cache from settings (memory / mongo / redis / none)."""

    backend = settings.embedding.cache_backend
    if backend is EmbeddingCacheBackend.NONE:
        return NullEmbeddingCache()
    if backend is EmbeddingCacheBackend.MONGO and db is not None:
        return MongoEmbeddingCache(db)
    if backend is EmbeddingCacheBackend.MONGO:
        log.warning("Mongo embedding cache requested without a DB handle — using memory")
        return MemoryEmbeddingCache()
    if backend is EmbeddingCacheBackend.REDIS:
        log.warning("Redis embedding cache not yet wired — using memory")
        return MemoryEmbeddingCache()
    return MemoryEmbeddingCache()


def build_embedding_provider(
    settings: Settings,
    *,
    registry: ModelRegistry | None = None,
    metrics: MetricsSink | None = None,
    db: AsyncIOMotorDatabase | None = None,
    cache: EmbeddingCache | None = None,
) -> EmbeddingProvider:
    """Return the configured provider, wrapped in a cache unless disabled.

    Backwards compatible: existing callers pass only ``settings`` and get a
    working provider (hashing when the ml extra is absent).
    """

    base = build_base_embedding_provider(settings, registry=registry, metrics=metrics)
    if settings.embedding.cache_backend is EmbeddingCacheBackend.NONE:
        return base
    resolved_cache = cache if cache is not None else build_embedding_cache(settings, db=db)
    return CachedEmbeddingProvider(base, resolved_cache)
