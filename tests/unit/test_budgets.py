"""Performance budgets."""

from __future__ import annotations

from app.config.settings import CollectorSettings
from app.metrics.memory import InMemoryMetrics
from app.observability.budgets import BudgetChecker


def _checker() -> tuple[BudgetChecker, InMemoryMetrics]:
    metrics = InMemoryMetrics()
    budget = CollectorSettings(
        budget_response_ms=1000, budget_max_crawl_seconds=10, budget_import_min_rps=50
    )
    return BudgetChecker(budget, metrics=metrics), metrics


def test_collector_run_within_budget_is_clean() -> None:
    checker, metrics = _checker()
    assert checker.check_collector_run(avg_response_ms=200, crawl_seconds=1) == []
    assert metrics.snapshot().counters.get("budget_violations_total", 0) == 0


def test_collector_run_over_budget_flags_and_counts() -> None:
    checker, metrics = _checker()
    violations = checker.check_collector_run(avg_response_ms=5000, crawl_seconds=99)
    kinds = {v.metric for v in violations}
    assert kinds == {"response_ms", "crawl_seconds"}
    assert metrics.snapshot().counters["budget_violations_total"] == 2


def test_import_throughput_budget() -> None:
    checker, _ = _checker()
    assert checker.check_import(rows=1000, seconds=1) == []  # 1000 rps ok
    slow = checker.check_import(rows=10, seconds=10)  # 1 rps < 50
    assert slow and slow[0].metric == "import_rps"
