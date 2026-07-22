"""In-memory cache provider behaviour."""

from __future__ import annotations

import pytest
from app.cache.memory import InMemoryCache


async def test_set_get_delete() -> None:
    cache = InMemoryCache()
    assert await cache.get("missing") is None

    await cache.set("k", {"v": 1})
    assert await cache.get("k") == {"v": 1}

    await cache.delete("k")
    assert await cache.get("k") is None


async def test_ttl_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = InMemoryCache()
    clock = {"now": 1000.0}
    monkeypatch.setattr("app.cache.memory.time.monotonic", lambda: clock["now"])

    await cache.set("k", "v", ttl_seconds=10)
    assert await cache.get("k") == "v"

    clock["now"] += 11  # advance past ttl
    assert await cache.get("k") is None


async def test_get_or_set_computes_once() -> None:
    cache = InMemoryCache()
    calls = {"n": 0}

    async def factory() -> int:
        calls["n"] += 1
        return 42

    assert await cache.get_or_set("k", factory) == 42
    assert await cache.get_or_set("k", factory) == 42
    assert calls["n"] == 1  # second call served from cache
