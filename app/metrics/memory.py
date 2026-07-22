"""In-memory metrics sink (default, thread-safe).

Process-local counters/gauges/summaries guarded by a lock. Backs ``/metrics``
for single-instance deployments and tests. Swap for a Prometheus-client-backed
sink (same port) when scraping/federation is needed.
"""

from __future__ import annotations

import threading
from collections import defaultdict

from app.metrics.base import MetricsSink, MetricsSnapshot, SummaryValue


class InMemoryMetrics(MetricsSink):
    """Thread-safe in-memory implementation of :class:`MetricsSink`."""

    backend = "memory"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._summaries: dict[str, SummaryValue] = defaultdict(SummaryValue)

    def increment(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] += value

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            summ = self._summaries[name]
            summ.count += 1
            summ.sum += value

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return MetricsSnapshot(
                counters=dict(self._counters),
                gauges=dict(self._gauges),
                summaries={k: v.model_copy() for k, v in self._summaries.items()},
            )

    def reset(self) -> None:
        """Clear all metrics (used by tests)."""

        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._summaries.clear()
