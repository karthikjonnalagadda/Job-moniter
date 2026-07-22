"""Async token-bucket rate limiter.

Smooths outbound request rate to a configured requests-per-second, allowing a
small burst up to ``capacity``. Shared per-host by the HTTP client so every
collector is rate-limited without implementing it itself.
"""

from __future__ import annotations

import asyncio
import time


class AsyncTokenBucket:
    """A refilling token bucket. ``rate <= 0`` disables limiting."""

    def __init__(self, rate: float, capacity: float | None = None) -> None:
        self._rate = rate
        self._capacity = capacity if capacity is not None else max(rate, 1.0)
        self._tokens = self._capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        """Block until ``tokens`` are available, then consume them."""

        if self._rate <= 0:
            return
        while True:
            async with self._lock:
                now = time.monotonic()
                self._tokens = min(
                    self._capacity, self._tokens + (now - self._updated) * self._rate
                )
                self._updated = now
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                wait = (tokens - self._tokens) / self._rate
            await asyncio.sleep(wait)
