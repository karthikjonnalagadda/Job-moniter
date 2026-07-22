"""Report history record — one per generated report/export."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.models.base import MongoDocument
from app.models.common import DEFAULT_USER_ID
from app.reports.versioning import REPORT_VERSION


class ReportFormat(StrEnum):
    EXCEL = "excel"
    CSV = "csv"
    JSON = "json"
    HTML = "html"
    PDF = "pdf"


class DeliveryStatus(StrEnum):
    GENERATED = "generated"
    SENT = "sent"
    FAILED = "failed"
    PENDING = "pending"


class ReportRecord(MongoDocument):
    """Persisted history of a generated report (Phase-7 report history)."""

    report_id: str
    run_id: str | None = None
    user_id: str = DEFAULT_USER_ID
    generated_at: datetime | None = None
    format: ReportFormat
    recipient: str | None = None
    delivery_status: DeliveryStatus = DeliveryStatus.GENERATED
    file_location: str | None = None
    generation_time: float = 0.0  # seconds
    download_count: int = 0

    # Report versioning (stamped on every report).
    report_version: int = REPORT_VERSION
    schema_version: int = 1
    pipeline_version: str = "0.0.0"
    collector_versions: dict[str, str] = Field(default_factory=dict)
