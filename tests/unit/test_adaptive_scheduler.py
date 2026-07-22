"""Adaptive polling scheduler."""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.collector_benchmark import CollectorBenchmark
from app.registry.models import SourceDefinition
from app.scheduling.adaptive import AdaptiveScheduler

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _scheduler() -> AdaptiveScheduler:
    return AdaptiveScheduler(
        base_interval=3600, min_interval=300, max_interval=86400, now=lambda: _NOW
    )


def test_no_history_uses_base_interval() -> None:
    decision = _scheduler().decide("greenhouse")
    assert decision.interval_seconds == 3600
    assert decision.next_poll_at == _NOW.replace(hour=1)


def test_high_activity_shortens_interval() -> None:
    active = CollectorBenchmark(collector="greenhouse", runs=5, total_jobs_found=500)  # 100/run
    decision = _scheduler().decide("greenhouse", benchmark=active)
    assert decision.interval_seconds < 3600  # polled more frequently


def test_high_error_rate_backs_off() -> None:
    flaky = CollectorBenchmark(collector="greenhouse", runs=4, total_errors=4, total_jobs_found=4)
    decision = _scheduler().decide("greenhouse", benchmark=flaky)
    # error factor lengthens vs the same activity without errors
    healthy = CollectorBenchmark(collector="greenhouse", runs=4, total_errors=0, total_jobs_found=4)
    healthy_decision = _scheduler().decide("greenhouse", benchmark=healthy)
    assert decision.interval_seconds > healthy_decision.interval_seconds


def test_clamped_to_bounds() -> None:
    huge = CollectorBenchmark(collector="x", runs=1, total_errors=1, total_jobs_found=0)
    src = SourceDefinition(name="x", rate_limit_rps=2.0)
    decision = _scheduler().decide("x", benchmark=huge, source=src)
    assert 300 <= decision.interval_seconds <= 86400
