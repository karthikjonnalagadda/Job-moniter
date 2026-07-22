"""Index definitions and idempotent creation helpers.

Two kinds of indexes:

1. **Standard indexes** — created via Motor's ``create_index`` at startup or
   from a bootstrap script. Safe and idempotent.
2. **Atlas Vector Search index** — a *search* index (not a regular index). It
   is created via the Atlas Admin API / ``createSearchIndexes`` command and may
   take time to build. The definition lives here as the single source of truth;
   actual creation is wired in Phase 3. This module only *describes* it now.

Nothing here loads data or runs business logic — Phase 2 scaffolding only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pymongo import ASCENDING, DESCENDING, TEXT

from app.config.logging import get_logger

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

    from app.config.settings import Settings

log = get_logger("api")

# Standard (non-vector) indexes, keyed by collection name.
STANDARD_INDEXES: dict[str, list[dict[str, Any]]] = {
    "jobs": [
        {"keys": [("job_hash", ASCENDING)], "unique": True, "name": "uq_job_hash"},
        {"keys": [("posted_date", DESCENDING)], "name": "ix_posted_date"},
        {"keys": [("match.score", DESCENDING)], "name": "ix_match_score"},
        {"keys": [("status", ASCENDING), ("posted_date", DESCENDING)], "name": "ix_status_posted"},
        {"keys": [("company_id", ASCENDING)], "name": "ix_company_id"},
        {"keys": [("role", TEXT), ("description", TEXT)], "name": "tx_role_desc"},
    ],
    "companies": [
        {"keys": [("slug", ASCENDING)], "unique": True, "name": "uq_slug"},
        {"keys": [("ats_type", ASCENDING)], "name": "ix_ats_type"},
        {"keys": [("country", ASCENDING)], "name": "ix_country"},
        {"keys": [("active_status", ASCENDING)], "name": "ix_active"},
        {"keys": [("name", TEXT)], "name": "tx_name"},
    ],
    "ats_sources": [
        {"keys": [("ats_type", ASCENDING)], "name": "ix_ats_type"},
        {"keys": [("enabled", ASCENDING)], "name": "ix_enabled"},
    ],
    "applications": [
        {"keys": [("status", ASCENDING)], "name": "ix_status"},
        {"keys": [("job_id", ASCENDING)], "unique": True, "name": "uq_job_id"},
    ],
    "pipeline_runs": [
        {"keys": [("run_id", ASCENDING)], "unique": True, "name": "uq_run_id"},
        {"keys": [("started_at", DESCENDING)], "name": "ix_started_at"},
    ],
    "report_history": [
        {"keys": [("report_id", ASCENDING)], "unique": True, "name": "uq_report_id"},
        {"keys": [("generated_at", DESCENDING)], "name": "ix_generated_at"},
    ],
    "resume_embeddings": [
        {
            "keys": [("user_id", ASCENDING), ("resume_id", ASCENDING)],
            "unique": True,
            "name": "uq_user_resume",
        },
    ],
    "embedding_cache": [
        {"keys": [("created_at", DESCENDING)], "name": "ix_created_at"},
    ],
    "users": [
        {"keys": [("user_id", ASCENDING)], "unique": True, "name": "uq_user_id"},
        {"keys": [("email", ASCENDING)], "name": "ix_email"},
    ],
    "user_preferences": [
        {"keys": [("user_id", ASCENDING)], "unique": True, "name": "uq_user_id"},
    ],
    "app_config": [
        {
            "keys": [("user_id", ASCENDING), ("key", ASCENDING)],
            "unique": True,
            "name": "uq_user_key",
        },
    ],
    "dead_letters": [
        {"keys": [("replayed", ASCENDING), ("created_at", DESCENDING)], "name": "ix_replayed"},
        {"keys": [("import_id", ASCENDING)], "name": "ix_import_id"},
        {"keys": [("kind", ASCENDING)], "name": "ix_kind"},
    ],
    "import_history": [
        {"keys": [("import_id", ASCENDING)], "unique": True, "name": "uq_import_id"},
        {"keys": [("started_at", DESCENDING)], "name": "ix_started_at"},
    ],
    "collector_benchmarks": [
        {"keys": [("collector", ASCENDING)], "unique": True, "name": "uq_collector"},
    ],
    "raw_payloads": [
        {"keys": [("collector", ASCENDING)], "name": "ix_collector"},
        {
            "keys": [("created_at", DESCENDING)],
            "name": "ttl_created_at",
            "expireAfterSeconds": 60 * 60 * 24 * 14,  # 14-day retention (configurable)
        },
    ],
    "retry_queue": [
        {"keys": [("task_id", ASCENDING)], "unique": True, "name": "uq_task_id"},
        {"keys": [("status", ASCENDING), ("next_attempt_at", ASCENDING)], "name": "ix_due"},
    ],
    # Log collections: query by run and auto-expire after 90 days.
    **{
        coll: [
            {"keys": [("run_id", ASCENDING)], "name": "ix_run_id"},
            {
                "keys": [("created_at", DESCENDING)],
                "name": "ttl_created_at",
                "expireAfterSeconds": 60 * 60 * 24 * 90,
            },
        ]
        for coll in (
            "search_logs",
            "email_logs",
            "collector_logs",
            "scheduler_logs",
        )
    },
}


def atlas_vector_index_definition(settings: Settings) -> dict[str, Any]:
    """Return the Atlas ``vectorSearch`` index definition for ``jobs.embedding``.

    Used by the Phase 3 bootstrap (``createSearchIndexes``) or created manually
    in the Atlas UI. Kept here so index shape and app config never drift.
    """

    return {
        "name": settings.vector.index_name,
        "type": "vectorSearch",
        "definition": {
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": settings.vector.dimensions,
                    "similarity": settings.vector.similarity,
                },
                {"type": "filter", "path": "status"},
                {"type": "filter", "path": "work_mode"},
                {"type": "filter", "path": "location_tags"},
            ]
        },
    }


async def ensure_standard_indexes(db: AsyncIOMotorDatabase) -> int:
    """Create all standard indexes. Idempotent; safe to run on every startup.

    Resilient by design: a backend that doesn't support a particular index
    option (e.g. an in-memory mock, or a shared-tier restriction) logs a warning
    for that index instead of aborting startup. Returns the count created.
    """

    created = 0
    for collection, specs in STANDARD_INDEXES.items():
        for raw in specs:
            spec = dict(raw)
            keys = spec.pop("keys")
            try:
                await db[collection].create_index(keys, **spec)
                created += 1
            except Exception as exc:  # non-fatal: never block startup on an index
                log.warning(
                    "Index {}.{} skipped: {}", collection, spec.get("name", "?"), exc
                )
    log.info("Standard indexes ensured ({} across {} collections)", created, len(STANDARD_INDEXES))
    return created
