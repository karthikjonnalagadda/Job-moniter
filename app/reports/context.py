"""Build a template-friendly context dict from a ``ReportData``.

Shared by the HTML dashboard, the PDF report, and the email body so all three
present the same numbers. Jobs are flattened to rows; the biggest bar in each
chart is normalised to 100% for CSS bar widths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.exporters.rows import job_to_row

if TYPE_CHECKING:
    from app.models.analytics import CountStat
    from app.reports.dataset import ReportData


def _bars(stats: list[CountStat], limit: int = 8) -> list[dict[str, Any]]:
    top = stats[:limit]
    if not top:
        return []
    peak = max(s.count for s in top) or 1
    return [
        {"label": s.label, "count": s.count, "pct": round(100 * s.count / peak, 1)}
        for s in top
    ]


def report_context(data: ReportData, *, top_n: int = 25) -> dict[str, Any]:
    a = data.analytics
    generated = data.generated_at.strftime("%Y-%m-%d %H:%M UTC") if data.generated_at else ""
    return {
        "title": data.title,
        "generated_at": generated,
        "run_id": data.run_id or "—",
        "summary": {
            "total_jobs": a.total_jobs,
            "ranked_jobs": a.ranked_jobs,
            "new_today": data.new_today,
            "average_match": a.average_match,
            "duplicate_groups": len(data.duplicate_groups),
        },
        "top_companies": _bars(a.companies),
        "top_roles": _bars(a.roles),
        "top_skills": _bars(a.skills),
        "top_technologies": _bars(a.technologies),
        "skill_gap": _bars(data.skill_gap),
        "top_matches": [job_to_row(job) for job in data.top_matches[:top_n]],
        "salaries": [s.model_dump() for s in a.salaries],
        "versions": data.versions.model_dump(),
    }
