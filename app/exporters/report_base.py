"""Report-exporter contract (multi-section reports over a ``ReportData``).

Complements the row-oriented ``Exporter`` port: exporters that render a full,
multi-section report (Excel workbook, HTML dashboard, PDF) implement this, while
simple row dumps (CSV/JSON) also satisfy the base ``Exporter``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from app.models.report_record import ReportFormat

if TYPE_CHECKING:
    from app.reports.dataset import ReportData


class ReportExporter(ABC):
    """Render a ``ReportData`` to a file on disk."""

    format: ReportFormat
    extension: str = "bin"
    #: Rendered in-memory (HTML) is available without a file too.
    supports_string: bool = False

    @abstractmethod
    def export(self, data: ReportData, destination: Path) -> Path:
        """Write the report to ``destination`` and return the written path."""
