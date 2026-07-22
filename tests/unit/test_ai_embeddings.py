"""Phase-8 embedding layer: cache, cached wrapper, factory, ST provider guards."""

from __future__ import annotations

import pytest
from app.config.settings import (
    EmbeddingCacheBackend,
    EmbeddingProviderType,
    Settings,
)
from app.embeddings.cache import (
    MemoryEmbeddingCache,
    NullEmbeddingCache,
    content_key,
)
from app.embeddings.cached import CachedEmbeddingProvider
from app.embeddings.factory import (
    build_base_embedding_provider,
    build_embedding_cache,
    build_embedding_provider,
)
from app.embeddings.hashing import HashingEmbeddingProvider
from app.embeddings.provider import EmbeddingProvider
from app.embeddings.sentence_transformer import (
    EmbeddingModelUnavailable,
    SentenceTransformerProvider,
)

# These assertions describe the behaviour when the optional ``ml`` extra
# (torch + sentence-transformers) is NOT installed. When it IS installed, the
# real BAAI/bge-small-en-v1.5 model is available, so the absence-path tests are
# skipped rather than deleted (they still guard the lean-image / CI path).
_ML_PRESENT = SentenceTransformerProvider.available()
_skip_if_ml = pytest.mark.skipif(
    _ML_PRESENT, reason="ml extra installed — absence-path behaviour not exercised"
)


def _settings(**embed: object) -> Settings:
    base: dict[str, object] = {
        "provider": EmbeddingProviderType.HASHING,
        "cache_backend": EmbeddingCacheBackend.MEMORY,
    }
    base.update(embed)
    return Settings(embedding=base)  # type: ignore[arg-type]


def test_content_key_is_deterministic_and_model_scoped() -> None:
    assert content_key("m1", "hello") == content_key("m1", "hello")
    assert content_key("m1", "hello") != content_key("m2", "hello")
    assert content_key("m1", "a") != content_key("m1", "b")


async def test_memory_cache_hit_miss_and_stats() -> None:
    cache = MemoryEmbeddingCache()
    assert await cache.get("k") is None
    await cache.set("k", [1.0, 2.0])
    assert await cache.get("k") == [1.0, 2.0]
    stats = await cache.stats()
    assert stats.hits == 1 and stats.misses == 1 and stats.size == 1
    assert stats.hit_rate == 0.5


async def test_null_cache_never_stores() -> None:
    cache = NullEmbeddingCache()
    await cache.set("k", [1.0])
    assert await cache.get("k") is None
    assert (await cache.stats()).backend == "none"


async def test_cached_provider_serves_second_call_from_cache() -> None:
    class _Counting(HashingEmbeddingProvider):
        calls = 0

        def embed_documents(self, texts):  # type: ignore[no-untyped-def]
            _Counting.calls += 1
            return super().embed_documents(texts)

    cache = MemoryEmbeddingCache()
    provider = CachedEmbeddingProvider(_Counting(dimensions=64), cache)
    first = await provider.aembed_documents(["python", "rust"])
    second = await provider.aembed_documents(["python", "rust"])
    assert first == second
    # Only the first call reached the delegate; the second was fully cached.
    assert _Counting.calls == 1
    stats = await cache.stats()
    assert stats.hits >= 2


async def test_cached_query_roundtrip() -> None:
    provider = CachedEmbeddingProvider(
        HashingEmbeddingProvider(dimensions=32), MemoryEmbeddingCache()
    )
    v1 = await provider.aembed_query("resume text")
    v2 = await provider.aembed_query("resume text")
    assert v1 == v2 and len(v1) == 32


@_skip_if_ml
def test_factory_auto_falls_back_to_hashing_without_ml() -> None:
    provider = build_base_embedding_provider(_settings(provider=EmbeddingProviderType.AUTO))
    assert isinstance(provider, HashingEmbeddingProvider)
    assert provider.model_name == "hashing"


@_skip_if_ml
def test_factory_forced_st_falls_back_when_unavailable() -> None:
    # ml extra is not installed in CI → fallback to hashing (fallback_to_hashing default True).
    provider = build_base_embedding_provider(
        _settings(provider=EmbeddingProviderType.SENTENCE_TRANSFORMER)
    )
    assert isinstance(provider, HashingEmbeddingProvider)


@_skip_if_ml
def test_factory_forced_st_without_fallback_raises() -> None:
    with pytest.raises(EmbeddingModelUnavailable):
        build_base_embedding_provider(
            _settings(
                provider=EmbeddingProviderType.SENTENCE_TRANSFORMER, fallback_to_hashing=False
            )
        )


def test_factory_wraps_in_cache_and_none_backend_does_not() -> None:
    wrapped = build_embedding_provider(_settings(cache_backend=EmbeddingCacheBackend.MEMORY))
    assert isinstance(wrapped, CachedEmbeddingProvider)
    plain = build_embedding_provider(_settings(cache_backend=EmbeddingCacheBackend.NONE))
    assert not isinstance(plain, CachedEmbeddingProvider)


def test_build_cache_backends() -> None:
    def backend(kind: EmbeddingCacheBackend) -> str:
        return build_embedding_cache(_settings(cache_backend=kind)).backend

    assert backend(EmbeddingCacheBackend.MEMORY) == "memory"
    assert backend(EmbeddingCacheBackend.NONE) == "none"
    # Mongo requested without a DB handle → memory fallback; Redis is reserved.
    assert backend(EmbeddingCacheBackend.MONGO) == "memory"
    assert backend(EmbeddingCacheBackend.REDIS) == "memory"


@_skip_if_ml
def test_st_provider_available_is_false_in_ci() -> None:
    assert SentenceTransformerProvider.available() is False


@_skip_if_ml
def test_st_provider_raises_without_model() -> None:
    provider = SentenceTransformerProvider(model_name="BAAI/bge-small-en-v1.5", dimensions=384)
    with pytest.raises(EmbeddingModelUnavailable):
        provider.embed_documents(["hello"])


def test_st_provider_batching_respects_count_and_chars() -> None:
    provider = SentenceTransformerProvider(batch_size=2, max_batch_chars=10)
    # count cap: 2 per batch
    batches = provider._batches(["a", "b", "c"])
    assert [len(b) for b in batches] == [2, 1]
    # char cap: "aaaaaa"(6) + "bbbbbb"(6) > 10 → split
    batches = provider._batches(["aaaaaa", "bbbbbb"])
    assert len(batches) == 2


def test_st_provider_resolves_cpu_device() -> None:
    provider = SentenceTransformerProvider(device="cpu")
    assert provider._resolve_device() == "cpu"
    auto = SentenceTransformerProvider(device="auto")
    assert auto._resolve_device() in ("cpu", "cuda")


async def test_hashing_health_check_and_warmup() -> None:
    provider: EmbeddingProvider = HashingEmbeddingProvider(dimensions=16)
    assert await provider.health_check() is True
    await provider.warmup()  # no-op, must not raise
