"""Retry policy for the shared HTTP client.

A declarative, immutable policy so retry behaviour is configured, not coded, in
each collector. Computes exponential backoff with jitter and decides whether a
given response/exception is retryable.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Exponential-backoff retry configuration."""

    max_retries: int = 3
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 30.0
    jitter_ratio: float = 0.1
    retry_statuses: frozenset[int] = field(
        default_factory=lambda: frozenset({429, 500, 502, 503, 504})
    )

    def should_retry_status(self, status_code: int) -> bool:
        return status_code in self.retry_statuses

    def backoff_for(self, attempt: int) -> float:
        """Delay before ``attempt`` (0-indexed) with capped exponential + jitter."""

        raw = self.backoff_base_seconds * (2**attempt)
        capped = min(self.backoff_max_seconds, raw)
        jitter = capped * self.jitter_ratio
        return capped + random.uniform(0.0, jitter)
