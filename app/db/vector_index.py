"""Atlas Vector Search index bootstrap.

The ``jobs.embedding`` vector index is an Atlas *search* index (not a regular
index), created with the ``createSearchIndexes`` command and built
asynchronously by Atlas. This module creates it idempotently and is a no-op on
non-Atlas deployments (local MongoDB / mongomock), where the command is
unsupported — so tests and local dev never fail here.

The index *definition* is the single source of truth in ``app.db.indexes``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.config.logging import get_logger
from app.db.indexes import atlas_vector_index_definition

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

    from app.config.settings import Settings

log = get_logger("api")


async def list_search_indexes(db: AsyncIOMotorDatabase, collection: str = "jobs") -> list[str]:
    """Return existing Atlas Search index names for ``collection`` (empty if none/unsupported)."""

    try:
        cursor = db[collection].list_search_indexes()
        return [idx["name"] async for idx in cursor]
    except Exception as exc:  # unsupported on local/mongomock — treat as "none"
        log.debug("list_search_indexes unavailable ({}): {}", collection, exc)
        return []


async def ensure_vector_index(
    db: AsyncIOMotorDatabase,
    settings: Settings,
    *,
    collection: str = "jobs",
) -> bool:
    """Create the Atlas vectorSearch index on ``jobs.embedding`` if missing.

    Returns True if a creation request was issued, False if it already existed or
    the backend doesn't support Atlas Search (local/mongomock — a safe no-op).
    """

    definition = atlas_vector_index_definition(settings)
    index_name = definition["name"]

    existing = await list_search_indexes(db, collection)
    if index_name in existing:
        log.info("Vector index '{}' already present", index_name)
        return False

    model: dict[str, Any] = {
        "name": index_name,
        "type": "vectorSearch",
        "definition": definition["definition"],
    }
    try:
        await db[collection].create_search_index(model)
        log.info("Vector index '{}' creation requested (builds asynchronously)", index_name)
        return True
    except Exception as exc:  # non-Atlas backend or insufficient tier
        log.warning(
            "Vector index not created (backend may not support Atlas Search): {}", exc
        )
        return False
