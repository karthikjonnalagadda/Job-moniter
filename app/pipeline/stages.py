"""Pipeline stage protocol + the collect stage."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.config.logging import get_logger

if TYPE_CHECKING:
    from app.collectors.base import CollectorTarget, RawJob
    from app.collectors.executor import CollectorExecutor

log = get_logger("collectors")


@runtime_checkable
class PipelineStage(Protocol):
    """A pipeline stage: explicit input in, explicit output out, no shared state."""

    name: str

    async def run(self, payload: object) -> object: ...


class CollectStage:
    """Collect stage: (collector, targets) work-list → collected ``RawJob``s.

    Delegates to the ``CollectorExecutor`` which isolates each collector, so a
    single failing source never interrupts the others. Distributable: the
    work-list is a plain serialisable input and the output is a plain list.
    """

    name = "collect"

    def __init__(self, executor: CollectorExecutor) -> None:
        self._executor = executor

    async def run(
        self, work: list[tuple[str, list[CollectorTarget]]]
    ) -> list[RawJob]:
        results = await self._executor.run_many(work)
        collected: list[RawJob] = []
        for result in results:
            collected.extend(result.jobs)
        log.info(
            "Collect stage: {} collectors, {} jobs, {} failed",
            len(results),
            len(collected),
            sum(1 for r in results if not r.ok),
        )
        return collected
