"""Import history model (import versioning).

One record per import run, stored in ``import_history``, so every import is
auditable and traceable: what file, its checksum, who ran it, how long it took,
and whether it rolled back. Lives in the importers package (not ``app.models``)
so it can embed ``ImportStats`` without a circular import.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.importers.models import ImportStats
from app.models.base import MongoDocument
from app.models.common import DEFAULT_USER_ID


class ImportRecord(MongoDocument):
    import_id: str  # unique per run
    filename: str | None = None
    checksum: str | None = None  # sha256 of the source file
    user_id: str = DEFAULT_USER_ID
    started_at: datetime | None = None
    duration_seconds: float = 0.0
    dry_run: bool = False
    rolled_back: bool = False
    stats: ImportStats = Field(default_factory=ImportStats)
