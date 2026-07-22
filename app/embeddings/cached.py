"""Caching decorator for any ``EmbeddingProvider``.

Wraps a delegate provider with an ``EmbeddingCache`` (content hash → vector).
The async surface (``aembed_documents`` / ``aembed_query``) is cache-aware: it
looks up every text by content key, embeds only the misses, writes them back,
and reassembles results in the original order — this is what delivers the
>95% cache-hit target and makes re-embedding a no-op.

The **sync** surface passes straight through to the delegate. Synchronous
callers (the batch pipeline) run inside an already-running event loop, so doing
async cache I/O there would risk reentrancy; those callers embed once anyway and
rely on the service-layer incremental logic instead. Same port, so it is a
drop-in wrapper (Decorator pattern).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.embeddings.cache import EmbeddingCache, content_key
from app.embeddings.provider import EmbeddingProvider


class CachedEmbeddingProvider(EmbeddingProvider):
    """Read-through cache in front of a delegate embedding provider."""

    def __init__(self, delegate: EmbeddingProvider, cache: EmbeddingCache) -> None:
        self._delegate = delegate
        self._cache = cache
        self.model_name = delegate.model_name
        self.dimensions = delegate.dimensions

    @property
    def delegate(self) -> EmbeddingProvider:
        return self._delegate

    @property
    def cache(self) -> EmbeddingCache:
        return self._cache

    # ---- sync pass-through ---------------------------------------------
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._delegate.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._delegate.embed_query(text)

    # ---- async, cache-aware --------------------------------------------
    async def aembed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        items = list(texts)
        if not items:
            return []
        # dimensions may only be known after the delegate loads; use current view.
        keys = [content_key(self._delegate.model_name, t or "") for t in items]
        cached = await self._cache.get_many(keys)

        misses = [(i, items[i]) for i, key in enumerate(keys) if key not in cached]
        if misses:
            embedded = await self._delegate.aembed_documents([t for _, t in misses])
            to_store: dict[str, list[float]] = {}
            for (idx, _), vector in zip(misses, embedded, strict=True):
                cached[keys[idx]] = vector
                to_store[keys[idx]] = vector
            await self._cache.set_many(to_store)

        # keep model_name/dimensions in sync with the (possibly now-loaded) delegate
        self.dimensions = self._delegate.dimensions
        return [cached[key] for key in keys]

    async def aembed_query(self, text: str) -> list[float]:
        key = content_key(self._delegate.model_name, f"query::{text or ''}")
        hit = await self._cache.get(key)
        if hit is not None:
            return hit
        vector = await self._delegate.aembed_query(text)
        await self._cache.set(key, vector)
        self.dimensions = self._delegate.dimensions
        return vector

    # ---- lifecycle proxying --------------------------------------------
    async def warmup(self) -> None:
        await self._delegate.warmup()
        self.dimensions = self._delegate.dimensions

    async def health_check(self) -> bool:
        return await self._delegate.health_check()
