"""Daily pipeline CLI entrypoint.

GitHub Actions invokes this every morning (06:00 IST) via the ``job-agent-daily``
console script. It boots configuration, logging, and the DB connection, then
runs the end-to-end daily pipeline (collect → normalize → filter → dedup →
embed → rank → store → report → email) implemented in
``app.scheduler.daily_pipeline``. The run is idempotent (a second run on the same
day that already succeeded is skipped), audited to the ``scheduler_logs``
collection, and fails gracefully — the process exits non-zero only on a hard
failure so the CI job surfaces it.
"""

from __future__ import annotations

import asyncio

from app.api.deps import build_container
from app.config.logging import configure_logging, get_logger
from app.config.settings import get_settings
from app.models.enums import RunStatus
from app.scheduler.daily_pipeline import run_daily_pipeline

log = get_logger("scheduler")


async def _run() -> int:
    settings = get_settings()
    configure_logging(settings)
    container = build_container(settings)
    log.info("Daily run starting [env={}]", settings.env)

    await container.mongo.connect()
    try:
        if not await container.mongo.ping():
            log.error("MongoDB unreachable — aborting daily run")
            return 1
        result = await run_daily_pipeline(container)
        # Exit non-zero on hard failure so the scheduler/CI marks the run failed.
        return 1 if result.status == RunStatus.FAILED else 0
    finally:
        await container.http.aclose()
        await container.mongo.disconnect()
        log.info("Daily run finished")


def main() -> None:
    """Synchronous console-script entrypoint."""

    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
