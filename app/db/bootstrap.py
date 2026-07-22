"""Database bootstrap orchestration.

One idempotent entrypoint that prepares a database for use:

1. standard indexes (always),
2. the Atlas vector index (optional; no-op off Atlas),
3. seed rows — the default user and a default config document — so the
   single-user MVP is functional immediately.

Called at API startup (indexes only, cheap/idempotent) and by the
``job-agent-bootstrap`` CLI (full, including the vector index) for first-time
Atlas provisioning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.config.logging import get_logger
from app.db.indexes import ensure_standard_indexes
from app.db.repositories.config import ConfigRepository
from app.db.repositories.users import UserRepository
from app.db.vector_index import ensure_vector_index
from app.models.app_config import AppConfigDocument

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

    from app.config.settings import Settings

log = get_logger("api")


@dataclass(slots=True)
class BootstrapResult:
    indexes_created: int
    vector_index_requested: bool
    default_user_ready: bool
    default_config_ready: bool


async def bootstrap_database(
    db: AsyncIOMotorDatabase,
    settings: Settings,
    *,
    with_vector_index: bool = False,
    seed: bool = True,
) -> BootstrapResult:
    """Prepare ``db``: indexes, optional vector index, and optional seed rows."""

    indexes = await ensure_standard_indexes(db)

    vector_requested = False
    if with_vector_index:
        vector_requested = await ensure_vector_index(db, settings)

    user_ready = False
    config_ready = False
    if seed:
        user = await UserRepository(db).ensure_default(
            email=settings.smtp.to_address or "owner@example.com"
        )
        user_ready = user is not None

        config_repo = ConfigRepository(db)
        if await config_repo.get_active() is None:
            await config_repo.save(AppConfigDocument())
        config_ready = True

    log.info(
        "Bootstrap complete (indexes={}, vector={}, seeded={})",
        indexes,
        vector_requested,
        seed,
    )
    return BootstrapResult(
        indexes_created=indexes,
        vector_index_requested=vector_requested,
        default_user_ready=user_ready,
        default_config_ready=config_ready,
    )
