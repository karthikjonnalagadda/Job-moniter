"""Exporter registry — resolve a ``ReportFormat`` to a configured exporter."""

from __future__ import annotations

from typing import Any

from app.exporters.csv_exporter import CsvExporter
from app.exporters.excel import ExcelExporter
from app.exporters.html import HtmlExporter
from app.exporters.json_exporter import JsonExporter
from app.exporters.pdf import PdfExporter
from app.exporters.report_base import ReportExporter
from app.models.report_record import ReportFormat


def build_exporter(fmt: ReportFormat | str, **options: Any) -> ReportExporter:
    """Return an exporter for ``fmt``, passing ``options`` to its constructor."""

    fmt = ReportFormat(fmt)
    if fmt == ReportFormat.EXCEL:
        return ExcelExporter()
    if fmt == ReportFormat.CSV:
        return CsvExporter(compress=bool(options.get("compress", False)))
    if fmt == ReportFormat.JSON:
        return JsonExporter(
            pretty=bool(options.get("pretty", True)),
            streaming=bool(options.get("streaming", False)),
        )
    if fmt == ReportFormat.HTML:
        return HtmlExporter(theme=str(options.get("theme", "default")))
    if fmt == ReportFormat.PDF:
        return PdfExporter()
    raise ValueError(f"Unsupported report format: {fmt}")  # pragma: no cover
