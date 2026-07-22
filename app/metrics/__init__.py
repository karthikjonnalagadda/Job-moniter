"""Application metrics.

Producers depend on the ``MetricsSink`` port; the ``/metrics`` endpoint reads a
``MetricsSnapshot``. Default backend is in-memory; a Prometheus exporter can be
added later behind the same port.
"""

from app.metrics.base import MetricsSink, MetricsSnapshot, SummaryValue
from app.metrics.memory import InMemoryMetrics

__all__ = ["InMemoryMetrics", "MetricsSink", "MetricsSnapshot", "SummaryValue"]
