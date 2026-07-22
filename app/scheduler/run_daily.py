"""Daily pipeline CLI entrypoint (skeleton).

GitHub Actions invokes this every morning (06:00 IST) via the ``job-agent-daily``
console script. The full orchestration (collect → normalize → dedup → rank →
store → export → email → log) is implemented by ``PipelineService`` in later
phases. Phase 2 provides only a runnable skeleton that boots configuration,
logging, and the DB connection, then exits cleanly.
"""

from __future__ import annotations

import asyncio

from app.api.deps import build_container
from app.config.logging import configure_logging, get_logger
from app.config.settings import get_settings

log = get_logger("scheduler")


async def _run() -> int:
    settings = get_settings()
    configure_logging(settings)
    container = build_container(settings)
    log.info("Daily run starting [env={}]", settings.env)

    await container.mongo.connect()
    try:
        reachable = await container.mongo.ping()
        log.info("Mongo reachable: {}", reachable)
        # TODO(Phase 8+): PipelineService(container).run()
        log.info("Pipeline not yet implemented — skeleton run complete")
        return 0
    finally:
        await container.mongo.disconnect()
        log.info("Daily run finished")


def main() -> None:
    """Synchronous console-script entrypoint."""

    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
