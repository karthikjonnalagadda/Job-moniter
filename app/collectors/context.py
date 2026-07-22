"""Execution context passed to the collector executor.

Bundles the shared collaborators a collector run needs. All optional except the
HTTP client, so the executor works in minimal setups (e.g. tests) and richer
production wiring alike.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.collectors.archive import RawArchiver
    from app.collectors.retry_queue import RetryQueue
    from app.collectors.state import CollectorStateRegistry
    from app.config.settings import Settings
    from app.db.repositories.benchmarks import BenchmarkRepository
    from app.http.client import HttpClient
    from app.observability.budgets import BudgetChecker


@dataclass(slots=True)
class CollectorContext:
    http: HttpClient
    settings: Settings
    archive: RawArchiver | None = None
    benchmarks: BenchmarkRepository | None = None
    states: CollectorStateRegistry | None = None
    retry_queue: RetryQueue | None = None
    budgets: BudgetChecker | None = None
