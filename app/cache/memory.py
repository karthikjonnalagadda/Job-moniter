"""In-memory cache provider (default).

Async-safe (guarded by a lock), with lazy TTL expiry. Suitable for a single
process / single instance. For multi-instance deployments, swap in a Redis
provider behind the same ``CacheProvider`` port — no service code changes.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from app.cache.base import CacheProvider


@dataclass(slots=True)
class _Entry:
    value: Any
    expires_at: float | None  # monotonic seconds; None = never expires


class InMemoryCache(CacheProvider):
    """Process-local dict cache with per-entry TTL."""

    backend = "memory"

    def __init__(self) -> None:
        self._store: dict[str, _Entry] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _expired(entry: _Entry, now: float) -> bool:
        return entry.expires_at is not None and entry.expires_at <= now

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if self._expired(entry, time.monotonic()):
                del self._store[key]
                return None
            return entry.value

    async def set(self, key: str, value: Any, *, ttl_seconds: float | None = None) -> None:
        expires_at = time.monotonic() + ttl_seconds if ttl_seconds else None
        async with self._lock:
            self._store[key] = _Entry(value=value, expires_at=expires_at)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()
