"""Performance budgets — SLA thresholds with warnings on breach.

Defines expected SLAs (avg collector response time, max crawl duration, minimum
import throughput) and reports violations. Violations are logged and counted in
metrics so dashboards/alerts can surface regressions. Budgets do not fail
operations — they observe.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config.logging import get_logger
from app.metrics.names import BUDGET_VIOLATIONS
from app.models.base import AppBaseModel

if TYPE_CHECKING:
    from app.config.settings import CollectorSettings
    from app.metrics.base import MetricsSink

log = get_logger("collectors")


class BudgetViolation(AppBaseModel):
    metric: str
    observed: float
    threshold: float
    message: str


class BudgetChecker:
    """Checks observed values against configured performance budgets."""

    def __init__(self, budget: CollectorSettings, *, metrics: MetricsSink | None = None) -> None:
        self._budget = budget
        self._metrics = metrics

    def _violation(
        self, metric: str, observed: float, threshold: float, message: str
    ) -> BudgetViolation:
        log.warning("Performance budget exceeded [{}]: {}", metric, message)
        if self._metrics is not None:
            self._metrics.increment(BUDGET_VIOLATIONS)
        return BudgetViolation(
            metric=metric, observed=observed, threshold=threshold, message=message
        )

    def check_collector_run(
        self, *, avg_response_ms: float | None, crawl_seconds: float
    ) -> list[BudgetViolation]:
        violations: list[BudgetViolation] = []
        limit_ms = self._budget.budget_response_ms
        if avg_response_ms is not None and avg_response_ms > limit_ms:
            violations.append(
                self._violation(
                    "response_ms",
                    avg_response_ms,
                    limit_ms,
                    f"avg response {avg_response_ms:.0f}ms > {limit_ms:.0f}ms",
                )
            )
        limit_s = self._budget.budget_max_crawl_seconds
        if crawl_seconds > limit_s:
            violations.append(
                self._violation(
                    "crawl_seconds",
                    crawl_seconds,
                    limit_s,
                    f"crawl {crawl_seconds:.1f}s > {limit_s:.1f}s",
                )
            )
        return violations

    def check_import(self, *, rows: int, seconds: float) -> list[BudgetViolation]:
        if seconds <= 0 or rows == 0:
            return []
        rps = rows / seconds
        limit = self._budget.budget_import_min_rps
        if rps < limit:
            return [
                self._violation(
                    "import_rps",
                    rps,
                    limit,
                    f"import throughput {rps:.1f} rows/s < {limit:.1f}",
                )
            ]
        return []
