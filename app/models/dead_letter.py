"""Dead-letter model.

Failed/malformed records (import rows that don't validate, collector fetches that
error) are written here instead of only being logged, so they can be inspected
and replayed. Stored in the ``dead_letters`` collection.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.models.base import MongoDocument


class DeadLetter(MongoDocument):
    kind: str  # "import_row" | "collector_fetch" | ...
    source: str  # filename or collector name
    reason: str
    error_code: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)  # the offending record
    import_id: str | None = None
    run_id: str | None = None
    correlation_id: str | None = None
    replayed: bool = False
