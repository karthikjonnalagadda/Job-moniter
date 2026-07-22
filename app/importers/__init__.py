"""Company import framework: parse → validate → upsert (CSV/JSON/YAML).

Supports dry-run, duplicate detection, per-row + cross-row validation, batch
upsert, rollback-on-failure, and import statistics — all behind
``CompanyImportService`` and the ``CompanyValidator``.
"""

from app.importers.aliases import AliasResolver
from app.importers.models import (
    ImportOptions,
    ImportReport,
    ImportStats,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
)
from app.importers.service import CompanyImportService
from app.importers.validation import CompanyValidator

__all__ = [
    "AliasResolver",
    "CompanyImportService",
    "CompanyValidator",
    "ImportOptions",
    "ImportReport",
    "ImportStats",
    "ValidationIssue",
    "ValidationReport",
    "ValidationSeverity",
]
