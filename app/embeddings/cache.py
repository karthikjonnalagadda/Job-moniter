"""Embedding cache — content hash → vector.

Embeddings are pure functions of ``(model, text)``, so they cache perfectly. The
cache key is a sha256 of the model name + text; a hit skips inference entirely
(this is what powers incremental embedding and the >95% hit-rate target).

Three interchangeable backends behind one port:
    * ``MemoryEmbeddingCache`` — process-local dict (default; fast, single node).
    * ``MongoEmbeddingCache`` — shared ``embedding_cache`` collection (survives
      restarts, shared across workers).
    * ``NullEmbeddingCache`` — disabled.

A Redis backend drops in behind the same port with no caller change (the factory
falls back to memory until a Redis client is wired).
"""

from __future__ import annotations

import hashlib
import threading
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.config.logging import get_logger
from app.models.base import AppBaseModel

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

log = get_logger("rank")


def content_key(model_name: str, text: str) -> str:
    """Deterministic cache key for one ``(model, text)`` pair."""

    digest = hashlib.sha256()
    digest.update(model_name.encode("utf-8"))
    digest.update(b"\x00")
    digest.update((text or "").encode("utf-8"))
    return digest.hexdigest()


class CacheStats(AppBaseModel):
    """Snapshot of cache effectiveness."""

    backend: str
    hits: int = 0
    misses: int = 0
    size: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 4) if total else 0.0


class EmbeddingCache(ABC):
    """Async content-hash → embedding store."""

    backend: str = "base"

    def __init__(self) -> None:
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    @abstractmethod
    async def _get(self, key: str) -> list[float] | None: ...

    @abstractmethod
    async def _set_many(self, items: dict[str, list[float]]) -> None: ...

    @abstractmethod
    async def _size(self) -> int: ...

    async def get(self, key: str) -> list[float] | None:
        value = await self._get(key)
        with self._lock:
            if value is None:
                self._misses += 1
            else:
                self._hits += 1
        return value

    async def get_many(self, keys: Sequence[str]) -> dict[str, list[float]]:
        """Return only the keys that are present (order-independent)."""

        found: dict[str, list[float]] = {}
        for key in keys:
            value = await self.get(key)
            if value is not None:
                found[key] = value
        return found

    async def set(self, key: str, vector: list[float]) -> None:
        await self._set_many({key: vector})

    async def set_many(self, items: dict[str, list[float]]) -> None:
        if items:
            await self._set_many(items)

    async def stats(self) -> CacheStats:
        with self._lock:
            hits, misses = self._hits, self._misses
        return CacheStats(
            backend=self.backend, hits=hits, misses=misses, size=await self._size()
        )


class NullEmbeddingCache(EmbeddingCache):
    """No-op cache (caching disabled)."""

    backend = "none"

    async def _get(self, key: str) -> list[float] | None:
        return None

    async def _set_many(self, items: dict[str, list[float]]) -> None:
        return None

    async def _size(self) -> int:
        return 0


class MemoryEmbeddingCache(EmbeddingCache):
    """Process-local dict cache with an optional LRU-ish size cap."""

    backend = "memory"

    def __init__(self, *, max_entries: int = 100_000) -> None:
        super().__init__()
        self._store: dict[str, list[float]] = {}
        self._max = max_entries

    async def _get(self, key: str) -> list[float] | None:
        return self._store.get(key)

    async def _set_many(self, items: dict[str, list[float]]) -> None:
        with self._lock:
            self._store.update(items)
            # Cheap bound: drop oldest insertions when over cap (dict is ordered).
            overflow = len(self._store) - self._max
            if overflow > 0:
                for key in list(self._store)[:overflow]:
                    del self._store[key]

    async def _size(self) -> int:
        return len(self._store)


class MongoEmbeddingCache(EmbeddingCache):
    """Shared cache backed by the ``embedding_cache`` collection."""

    backend = "mongo"
    _COLLECTION = "embedding_cache"

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__()
        self._col = db[self._COLLECTION]

    async def _get(self, key: str) -> list[float] | None:
        doc = await self._col.find_one({"_id": key}, {"vector": 1})
        if doc is None:
            return None
        vector = doc.get("vector")
        return list(vector) if vector is not None else None

    async def get_many(self, keys: Sequence[str]) -> dict[str, list[float]]:
        # One round-trip for the whole batch.
        cursor = self._col.find({"_id": {"$in": list(keys)}}, {"vector": 1})
        found: dict[str, list[float]] = {}
        async for doc in cursor:
            found[doc["_id"]] = list(doc["vector"])
        with self._lock:
            self._hits += len(found)
            self._misses += len(keys) - len(found)
        return found

    async def _set_many(self, items: dict[str, list[float]]) -> None:
        now = datetime.now(tz=UTC)
        try:
            for key, vector in items.items():
                await self._col.update_one(
                    {"_id": key},
                    {"$set": {"vector": vector, "created_at": now}},
                    upsert=True,
                )
        except Exception as exc:  # cache writes must never break embedding
            log.warning("Embedding cache write failed: {}", exc)

    async def _size(self) -> int:
        try:
            return int(await self._col.estimated_document_count())
        except Exception:
            return 0
