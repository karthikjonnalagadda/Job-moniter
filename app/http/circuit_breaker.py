"""Circuit breaker for the shared HTTP client.

Prevents hammering a failing source. Classic three-state machine:

* **closed**    — requests flow; consecutive failures are counted.
* **open**      — after ``failure_threshold`` failures, reject immediately for
  ``reset_timeout`` seconds (fail fast, let the source recover).
* **half-open** — after the cooldown, allow a limited number of trial requests;
  a success closes the circuit, a failure re-opens it.

One breaker is kept per host by the HTTP client. Time is injected (``monotonic``)
so it is deterministically testable.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class CircuitBreakerConfig:
    failure_threshold: int = 5  # consecutive failures before opening
    reset_timeout: float = 30.0  # seconds to stay open before half-open
    half_open_max_calls: int = 1  # trial calls allowed while half-open


class CircuitBreaker:
    """Per-host circuit breaker. Not coroutine-reentrant; guard externally if needed."""

    def __init__(
        self,
        config: CircuitBreakerConfig | None = None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config or CircuitBreakerConfig()
        self._now = monotonic
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        self._maybe_half_open()
        return self._state

    def _maybe_half_open(self) -> None:
        if self._state is CircuitState.OPEN and (
            self._now() - self._opened_at >= self._config.reset_timeout
        ):
            self._state = CircuitState.HALF_OPEN
            self._half_open_calls = 0

    def allow(self) -> bool:
        """Return True if a request may proceed right now."""

        self._maybe_half_open()
        if self._state is CircuitState.CLOSED:
            return True
        if self._state is CircuitState.OPEN:
            return False
        # half-open: allow a bounded number of trial calls
        if self._half_open_calls < self._config.half_open_max_calls:
            self._half_open_calls += 1
            return True
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._half_open_calls = 0

    def record_failure(self) -> None:
        self._failures += 1
        tripped = (
            self._state is CircuitState.HALF_OPEN
            or self._failures >= self._config.failure_threshold
        )
        if tripped:
            self._trip()

    def _trip(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._now()
        self._half_open_calls = 0
