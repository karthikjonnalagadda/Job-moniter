"""In-memory metrics sink + Prometheus rendering."""

from __future__ import annotations

from app.metrics.memory import InMemoryMetrics
from app.metrics.names import JOBS_COLLECTED, MATCH_SCORE, RANKING_DURATION


def test_counter_gauge_summary() -> None:
    m = InMemoryMetrics()
    m.increment(JOBS_COLLECTED, 3)
    m.increment(JOBS_COLLECTED)
    m.set_gauge("jobs_in_last_run", 4)
    m.observe(MATCH_SCORE, 80)
    m.observe(MATCH_SCORE, 90)

    snap = m.snapshot()
    assert snap.counters[JOBS_COLLECTED] == 4
    assert snap.gauges["jobs_in_last_run"] == 4
    assert snap.summaries[MATCH_SCORE].count == 2
    assert snap.averages()[MATCH_SCORE] == 85


def test_timer_records_summary() -> None:
    m = InMemoryMetrics()
    with m.timer(RANKING_DURATION):
        pass
    assert m.snapshot().summaries[RANKING_DURATION].count == 1


def test_prometheus_render() -> None:
    m = InMemoryMetrics()
    m.increment(JOBS_COLLECTED, 2)
    text = m.render_prometheus()
    assert f"# TYPE {JOBS_COLLECTED} counter" in text
    assert f"{JOBS_COLLECTED} 2" in text
