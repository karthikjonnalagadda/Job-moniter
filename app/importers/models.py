"""Import + validation data models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, computed_field

from app.models.base import AppBaseModel


class ValidationSeverity(StrEnum):
    ERROR = "error"  # blocks import of the row (unless skip_invalid)
    WARNING = "warning"  # imported, but flagged


class ValidationIssue(AppBaseModel):
    """One problem found with a company record."""

    code: str  # machine code, e.g. "duplicate_slug", "malformed_url"
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    row: int | None = None  # 1-based row/index in the source
    slug: str | None = None
    field: str | None = None


class ValidationReport(AppBaseModel):
    """Outcome of validating a batch of company records."""

    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    issues: list[ValidationIssue] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]  # serialised in API responses
    @property
    def is_valid(self) -> bool:
        return not any(i.severity == ValidationSeverity.ERROR for i in self.issues)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]


class ImportOptions(AppBaseModel):
    """Knobs controlling an import run."""

    dry_run: bool = False  # parse+validate only, write nothing
    overwrite: bool = True  # upsert existing slugs (False => skip existing)
    skip_invalid: bool = False  # import valid rows, skip invalid ones
    batch_size: int = 500
    rollback_on_failure: bool = True  # undo this run's inserts if apply fails


class ImportStats(AppBaseModel):
    """Counters produced by an import run."""

    total: int = 0  # rows read from the file
    valid: int = 0
    invalid: int = 0
    duplicates: int = 0  # duplicate keys within the file
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0


class ImportReport(AppBaseModel):
    """Full result of an import run."""

    import_id: str | None = None
    source_file: str | None = None
    checksum: str | None = None
    dry_run: bool = False
    rolled_back: bool = False
    duration_seconds: float = 0.0
    stats: ImportStats = Field(default_factory=ImportStats)
    validation: ValidationReport = Field(default_factory=ValidationReport)
