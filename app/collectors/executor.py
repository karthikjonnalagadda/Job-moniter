"""Collector executor — runs one collector against its targets in isolation.

Responsibilities (all cross-cutting, none source-specific):

* instantiate the collector with the shared HTTP client + archiver;
* drive its lifecycle **state machine** (SYNCING → IDLE / RATE_LIMITED / FAILED);
* isolate failures per target and per collector (**bulkhead**) so one broken
  source never interrupts the rest;
* enqueue failed fetches to the **retry queue**;
* record **benchmark** stats and capture the incremental **sync watermark**;
* check **performance budgets**.

The executor is stateless between calls and takes all inputs explicitly, so a
run could later be dispatched to a separate worker with no business-logic change
(distributed-execution readiness).
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from pydantic import Field

from app.collectors.ats.base_ats import BaseATSCollector
from app.collectors.base import RawJob
from app.collectors.registry import get_collector_class
from app.collectors.state import CollectorState
from app.config.logging import get_logger
from app.core.exceptions import CircuitOpenError, RateLimitError
from app.models.base import AppBaseModel

if TYPE_CHECKING:
    from app.collectors.base import BaseCollector, CollectorTarget
    from app.collectors.context import CollectorContext
    from app.collectors.state import CollectorStateMachine

log = get_logger("collectors")


class CollectorRunResult(AppBaseModel):
    collector: str
    ok: bool
    jobs_found: int
    duplicates: int
    errors: int
    duration_seconds: float
    avg_response_ms: float
    state: CollectorState
    sync: dict[str, str | None]
    jobs: list[RawJob] = Field(default_factory=list)


class CollectorExecutor:
    def __init__(self, context: CollectorContext) -> None:
        self._ctx = context

    def _instantiate(self, name: str) -> BaseCollector:
        cls = get_collector_class(name)
        if issubclass(cls, BaseATSCollector):
            return cls(self._ctx.http, archive=self._ctx.archive)
        return cls()  # e.g. the disabled LinkedIn stub (no deps)

    async def run(self, name: str, targets: list[CollectorTarget]) -> CollectorRunResult:
        machine = self._ctx.states.get(name) if self._ctx.states else None
        if machine is not None:
            machine.transition(CollectorState.SYNCING)

        collector = self._instantiate(name)
        started = time.perf_counter()
        jobs: list[RawJob] = []
        errors = 0
        throttled = False

        for target in targets:
            try:
                jobs.extend(await collector.search(target))
            except (CircuitOpenError, RateLimitError) as exc:
                errors += 1
                throttled = True
                log.warning("{}: throttled on target: {}", name, exc)
                await self._enqueue_retry(name, target, str(exc))
            except Exception as exc:  # isolate any collector failure
                errors += 1
                log.error("{}: fetch failed: {}", name, exc)
                await self._enqueue_retry(name, target, str(exc))

        duration = time.perf_counter() - started
        avg_response_ms = (duration * 1000.0) / max(1, len(targets))
        duplicates = len(jobs) - len({j.external_id for j in jobs})

        if self._ctx.benchmarks is not None:
            await self._ctx.benchmarks.record_run(
                name,
                jobs_found=len(jobs),
                duplicates=duplicates,
                errors=errors,
                response_ms=avg_response_ms,
            )

        if self._ctx.budgets is not None:
            self._ctx.budgets.check_collector_run(
                avg_response_ms=avg_response_ms, crawl_seconds=duration
            )

        final_state = self._resolve_state(machine, jobs=jobs, errors=errors, throttled=throttled)
        sync = collector.sync_watermark() if isinstance(collector, BaseATSCollector) else {}

        return CollectorRunResult(
            collector=name,
            ok=errors == 0,
            jobs_found=len(jobs),
            duplicates=duplicates,
            errors=errors,
            duration_seconds=round(duration, 4),
            avg_response_ms=round(avg_response_ms, 2),
            state=final_state,
            sync=sync,
            jobs=jobs,
        )

    def _resolve_state(
        self,
        machine: CollectorStateMachine | None,
        *,
        jobs: list[RawJob],
        errors: int,
        throttled: bool,
    ) -> CollectorState:
        if throttled:
            target = CollectorState.RATE_LIMITED
        elif errors and not jobs:
            target = CollectorState.FAILED
        else:
            target = CollectorState.IDLE
        if machine is not None:
            machine.transition(target)
        return target

    async def _enqueue_retry(self, name: str, target: CollectorTarget, error: str) -> None:
        if self._ctx.retry_queue is not None:
            await self._ctx.retry_queue.enqueue_failure(
                name, target.model_dump(), error=error
            )

    async def run_many(
        self, work: list[tuple[str, list[CollectorTarget]]]
    ) -> list[CollectorRunResult]:
        """Run several collectors concurrently, isolating each (bulkhead)."""

        async def _guard(name: str, targets: list[CollectorTarget]) -> CollectorRunResult:
            try:
                return await self.run(name, targets)
            except Exception as exc:  # a collector must never break the batch
                log.error("Collector '{}' crashed: {}", name, exc)
                return CollectorRunResult(
                    collector=name,
                    ok=False,
                    jobs_found=0,
                    duplicates=0,
                    errors=1,
                    duration_seconds=0.0,
                    avg_response_ms=0.0,
                    state=CollectorState.FAILED,
                    sync={},
                )

        return await asyncio.gather(*(_guard(n, t) for n, t in work))
