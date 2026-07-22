"""HTML dashboard exporter — email- and browser-ready single-file report.

Renders the Jinja2 ``report.html.j2`` template (inline CSS, CSS bar charts, no
external assets) so the same HTML works in a browser and inside an email body.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.exporters.report_base import ReportExporter
from app.models.report_record import ReportFormat
from app.reports.context import report_context
from app.reports.templating import TemplateRenderer

if TYPE_CHECKING:
    from app.reports.dataset import ReportData

_TEMPLATE = "report.html.j2"


class HtmlExporter(ReportExporter):
    """Render a ``ReportData`` to a self-contained HTML dashboard."""

    format = ReportFormat.HTML
    extension = "html"
    supports_string = True

    def __init__(
        self, *, theme: str = "default", renderer: TemplateRenderer | None = None
    ) -> None:
        self._theme = theme
        self._renderer = renderer or TemplateRenderer()

    def render(self, data: ReportData) -> str:
        return self._renderer.render(
            _TEMPLATE, report_context(data), theme_name=self._theme
        )

    def export(self, data: ReportData, destination: Path) -> Path:
        destination.write_text(self.render(data), encoding="utf-8")
        return destination
