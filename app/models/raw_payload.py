"""Raw payload archive model.

Stores the original upstream response (JSON/HTML) a collector fetched, so parser
bugs can be debugged without re-fetching. Retained for a configurable period via
a TTL index on ``created_at`` (see ``app.db.indexes``). Stored in ``raw_payloads``.
"""

from __future__ import annotations

from app.models.base import MongoDocument


class RawPayload(MongoDocument):
    collector: str  # collector name that fetched it
    source_slug: str | None = None  # company/board token
    url: str
    content_type: str | None = None
    status_code: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    body: str  # raw response text (JSON or HTML)
    run_id: str | None = None
    correlation_id: str | None = None
