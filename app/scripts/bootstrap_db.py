"""``job-agent-bootstrap`` — one-shot database provisioning CLI.

Creates standard indexes, the Atlas vector index (``--with-vector-index``), and
seeds the default user + config. Idempotent: safe to run repeatedly. Intended
for first-time Atlas setup and CI provisioning.

Usage:
    python -m app.scripts.bootstrap_db --with-vector-index
    job-agent-bootstrap --with-vector-index --no-seed
"""

from __future__ import annotations

import argparse
import asyncio

from app.api.deps import build_container
from app.config.logging import configure_logging, get_logger
from app.config.settings import get_settings
from app.db.bootstrap import bootstrap_database

log = get_logger("api")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap the AI Job Agent database.")
    parser.add_argument(
        "--with-vector-index",
        action="store_true",
        help="Also create the Atlas vectorSearch index (Atlas only).",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Skip seeding the default user and config document.",
    )
    return parser.parse_args()


async def _run(with_vector_index: bool, seed: bool) -> int:
    settings = get_settings()
    configure_logging(settings)
    container = build_container(settings)

    await container.mongo.connect()
    try:
        if not await container.mongo.ping():
            log.error("MongoDB not reachable — cannot bootstrap")
            return 1
        result = await bootstrap_database(
            container.mongo.db,
            settings,
            with_vector_index=with_vector_index,
            seed=seed,
        )
        log.info("Bootstrap result: {}", result)
        return 0
    finally:
        await container.mongo.disconnect()


def main() -> None:
    args = _parse_args()
    raise SystemExit(
        asyncio.run(_run(with_vector_index=args.with_vector_index, seed=not args.no_seed))
    )


if __name__ == "__main__":
    main()
