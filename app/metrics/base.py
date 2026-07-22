"""Metrics sink port + snapshot schema.

Three metric kinds cover the Phase 1 requirements without pulling in a metrics
library yet:

* **counter**  — monotonic totals (jobs collected, collectors failed, ...).
* **gauge**    — point-in-time values (jobs in last run, last-run timestamp).
* **summary**  — count + sum, yielding averages (ranking/email/scheduler
  duration, average match score).

The pipeline and API depend on this port. The in-memory implementation backs the
``/metrics`` endpoint today; a Prometheus client can implement the same port
later with zero call-site changes. ``render_prometheus`` already emits valid
exposition-format text so Prometheus can scrape ``/metrics`` immediately.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager

from app.models.base import AppBaseModel


class SummaryValue(AppBaseModel):
    count: int = 0
    sum: float = 0.0

    @property
    def average(self) -> float:
        return self.sum / self.count if self.count else 0.0


class MetricsSnapshot(AppBaseModel):
    """Immutable view of all metrics at a point in time (served by /metrics)."""

    counters: dict[str, float]
    gauges: dict[str, float]
    summaries: dict[str, SummaryValue]

    def averages(self) -> dict[str, float]:
        return {name: s.average for name, s in self.summaries.items()}


class MetricsSink(ABC):
    """Port for recording application metrics."""

    backend: str = "base"

    @abstractmethod
    def increment(self, name: str, value: float = 1.0) -> None:
        """Add ``value`` to a monotonic counter."""

    @abstractmethod
    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge to ``value``."""

    @abstractmethod
    def observe(self, name: str, value: float) -> None:
        """Record one observation into a summary (updates count and sum)."""

    @abstractmethod
    def snapshot(self) -> MetricsSnapshot:
        """Return a consistent snapshot of all metrics."""

    def render_prometheus(self) -> str:
        """Render the snapshot in Prometheus text exposition format."""

        snap = self.snapshot()
        lines: list[str] = []
        for name, val in sorted(snap.counters.items()):
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {val}")
        for name, val in sorted(snap.gauges.items()):
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name} {val}")
        for name, summ in sorted(snap.summaries.items()):
            lines.append(f"# TYPE {name} summary")
            lines.append(f"{name}_count {summ.count}")
            lines.append(f"{name}_sum {summ.sum}")
        return "\n".join(lines) + "\n"

    @contextmanager
    def timer(self, name: str) -> Iterator[None]:
        """Time the ``with`` block and ``observe`` its duration in seconds."""

        started = time.perf_counter()
        try:
            yield
        finally:
            self.observe(name, time.perf_counter() - started)
