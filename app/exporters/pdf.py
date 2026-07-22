"""PDF report exporter (reportlab, lazy-imported via the ``reports`` extra).

Sections: Executive Summary · Statistics · Top Matches · Charts · Company
Breakdown · Skill Gap Analysis. ``reportlab`` is imported lazily so the lean API
image works without the extra; ``PdfExporter.available()`` reports installation.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.exceptions import ConfigurationError
from app.exporters.report_base import ReportExporter
from app.models.report_record import ReportFormat
from app.reports.context import report_context

if TYPE_CHECKING:
    from app.reports.dataset import ReportData

_ACCENT = "#1F4E78"


class PdfExporter(ReportExporter):
    """Render a ``ReportData`` to a printable PDF."""

    format = ReportFormat.PDF
    extension = "pdf"

    @staticmethod
    def available() -> bool:
        try:
            import reportlab  # noqa: F401
        except ImportError:
            return False
        return True

    def export(self, data: ReportData, destination: Path) -> Path:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import Paragraph as P
            from reportlab.platypus import SimpleDocTemplate, Spacer
        except ImportError as exc:  # pragma: no cover - exercised only without extra
            raise ConfigurationError(
                "PDF export requires the 'reports' extra (pip install '.[reports]')"
            ) from exc

        ctx = report_context(data)
        styles = getSampleStyleSheet()
        accent = colors.HexColor(_ACCENT)
        story: list[Any] = []

        story.append(P(f"<b>{ctx['title']}</b>", styles["Title"]))
        story.append(P(f"Generated {ctx['generated_at']} — run {ctx['run_id']}", styles["Normal"]))
        story.append(Spacer(1, 0.4 * cm))

        # Executive summary + statistics.
        s = ctx["summary"]
        story.append(P("<b>Executive Summary</b>", styles["Heading2"]))
        summary_rows = [
            ["Total jobs", s["total_jobs"]],
            ["New today", s["new_today"]],
            ["Ranked jobs", s["ranked_jobs"]],
            ["Average match", s["average_match"]],
            ["Duplicate groups", s["duplicate_groups"]],
        ]
        story.append(self._table(summary_rows, colors, accent, header=False))
        story.append(Spacer(1, 0.4 * cm))

        # Charts (company breakdown as a bar chart).
        if ctx["top_companies"]:
            story.append(P("<b>Company Breakdown</b>", styles["Heading2"]))
            story.append(self._bar_chart(ctx["top_companies"], colors, accent))
            story.append(Spacer(1, 0.4 * cm))

        # Top matches.
        story.append(P("<b>Top Matches</b>", styles["Heading2"]))
        match_rows = [["Score", "Role", "Company", "Location"]]
        for job in ctx["top_matches"][:20]:
            match_rows.append(
                [job["match_score"], job["normalized_role"], job["company"], job["location"]]
            )
        story.append(self._table(match_rows, colors, accent, header=True))
        story.append(Spacer(1, 0.4 * cm))

        # Skill gap.
        if ctx["skill_gap"]:
            story.append(P("<b>Skill Gap Analysis</b>", styles["Heading2"]))
            gap_rows = [["Missing Skill", "Count"]] + [
                [g["label"], g["count"]] for g in ctx["skill_gap"]
            ]
            story.append(self._table(gap_rows, colors, accent, header=True))

        doc = SimpleDocTemplate(str(destination), pagesize=A4, title=ctx["title"])
        doc.build(story)
        return destination

    def _table(self, rows: list[list[Any]], colors: Any, accent: Any, *, header: bool) -> Any:
        from reportlab.platypus import Table, TableStyle

        table = Table(rows, hAlign="LEFT")
        style = [
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D7DE")),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#F4F6F9")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
        if header:
            style += [
                ("BACKGROUND", (0, 0), (-1, 0), accent),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        table.setStyle(TableStyle(style))
        return table

    def _bar_chart(self, items: list[dict[str, Any]], colors: Any, accent: Any) -> Any:
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        from reportlab.graphics.shapes import Drawing

        drawing = Drawing(440, 180)
        chart = VerticalBarChart()
        chart.x, chart.y, chart.width, chart.height = 30, 20, 380, 140
        chart.data = [[it["count"] for it in items]]
        chart.categoryAxis.categoryNames = [it["label"][:12] for it in items]
        chart.bars[0].fillColor = accent
        chart.valueAxis.valueMin = 0
        drawing.add(chart)
        return drawing
