"""Cache provider port.

A minimal async key/value contract with per-entry TTL. Deliberately small so
Redis and MongoDB adapters are trivial to add. Values are arbitrary Python
objects for the in-memory provider; networked providers serialise as needed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any


class CacheProvider(ABC):
    """Async key/value cache with optional TTL."""

    #: Backend identifier for diagnostics (``"memory"``, ``"redis"``, ...).
    backend: str = "base"

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Return the cached value or ``None`` if missing/expired."""

    @abstractmethod
    async def set(self, key: str, value: Any, *, ttl_seconds: float | None = None) -> None:
        """Store ``value`` under ``key``; expire after ``ttl_seconds`` if given."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove ``key`` if present (no error if absent)."""

    @abstractmethod
    async def clear(self) -> None:
        """Drop all entries."""

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        *,
        ttl_seconds: float | None = None,
    ) -> Any:
        """Return the cached value, or compute it via async ``factory`` and cache it.

        Provided on the port so every backend shares this read-through idiom.
        """

        cached = await self.get(key)
        if cached is not None:
            return cached
        produced = await factory()
        await self.set(key, produced, ttl_seconds=ttl_seconds)
        return produced
