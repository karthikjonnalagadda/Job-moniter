"""Job processing quality score.

Combines five signals into an overall processing confidence (0-1):

* ``parser``        — how cleanly the raw payload parsed (from the collector);
* ``normalization`` — confidence of the role/location/salary/etc. mapping;
* ``duplicate``     — ``1 - duplicate_confidence`` (1 = surely unique);
* ``collector``     — trust in the source collector;
* ``completeness``  — fraction of the key fields that are populated.

``missing_fields`` lists the key fields that were empty. The weights are simple
and transparent; the resulting ``overall`` mirrors ``Job.confidence_score``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.common import QualityScore

if TYPE_CHECKING:
    from app.models.job import Job

# Key fields whose presence defines a "complete" posting.
_KEY_FIELDS = (
    "company_name",
    "role",
    "url",
    "description",
    "location",
    "posted_date",
    "salary",
    "skills",
)

_WEIGHTS = {
    "parser": 0.20,
    "normalization": 0.25,
    "duplicate": 0.15,
    "collector": 0.15,
    "completeness": 0.25,
}


def _present(job: Job, field: str) -> bool:
    if field == "location":
        return bool(job.location.city or job.location.country or job.location.is_remote)
    if field in {"skills"}:
        return bool(getattr(job, field))
    return getattr(job, field, None) not in (None, "")


class QualityScorer:
    """Compute a ``QualityScore`` for a normalised job."""

    def score(
        self,
        job: Job,
        *,
        parser: float = 1.0,
        normalization: float = 1.0,
        duplicate_confidence: float = 0.0,
        collector: float = 1.0,
    ) -> QualityScore:
        missing = [f for f in _KEY_FIELDS if not _present(job, f)]
        completeness = 1.0 - len(missing) / len(_KEY_FIELDS)
        duplicate = 1.0 - max(0.0, min(1.0, duplicate_confidence))
        components = {
            "parser": _clamp(parser),
            "normalization": _clamp(normalization),
            "duplicate": duplicate,
            "collector": _clamp(collector),
            "completeness": completeness,
        }
        overall = sum(components[k] * _WEIGHTS[k] for k in _WEIGHTS)
        return QualityScore(
            parser=round(components["parser"], 4),
            normalization=round(components["normalization"], 4),
            duplicate=round(duplicate, 4),
            collector=round(components["collector"], 4),
            completeness=round(completeness, 4),
            overall=round(overall, 4),
            missing_fields=missing,
        )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
