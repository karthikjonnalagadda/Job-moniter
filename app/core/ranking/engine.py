"""Composite ranking engine + explainability.

Computes the ``MatchDetail`` for a job against a resume context as a weighted sum
of six components (weights from ``RankingSettings``, validated to sum to 1.0):

    Overall = 0.40·semantic + 0.20·skill + 0.15·experience
            + 0.10·location + 0.10·company_priority + 0.05·freshness

Each component is a 0-1 sub-score; ``MatchDetail.score`` is the 0-100 composite.
Every component also emits a human-readable explanation (Explainable AI), and the
matched/missing skills are attached so the UI can show *why* a job scored as it
did. Weights stay fully configurable via ``JOBAGENT_RANKING__WEIGHT_*``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import Field

from app.core.ranking.skill_gap import SkillGap, SkillGapAnalyzer
from app.core.similarity import cosine
from app.models.base import AppBaseModel
from app.models.enums import WorkMode
from app.models.job import MatchDetail

if TYPE_CHECKING:
    from app.config.settings import RankingSettings
    from app.models.job import Job

_FRESH_HORIZON_HOURS = 720.0  # 30 days → 0


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class ResumeContext(AppBaseModel):
    """Everything the ranker needs about the candidate for one resume version."""

    resume_id: str | None = None
    embedding: list[float] | None = None
    skills: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    preferred_work_modes: list[WorkMode] = Field(default_factory=list)
    max_experience_years: float = 2.0


class RankingEngine:
    """Score a job against a resume context into a ``MatchDetail``."""

    def __init__(
        self,
        weights: RankingSettings,
        *,
        gap_analyzer: SkillGapAnalyzer | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._w = weights
        self._gap = gap_analyzer or SkillGapAnalyzer()
        self._now = now or _utcnow

    def rank(
        self, job: Job, context: ResumeContext, *, company_priority: float = 0.5
    ) -> MatchDetail:
        similarity = cosine(context.embedding, job.embedding)
        gap = self._gap.analyze(context.skills, job.skills, job_technologies=job.technologies)
        skill = gap.coverage
        experience = self._experience_score(job, context.max_experience_years)
        location = self._location_score(job, context)
        company = _clamp(company_priority)
        freshness = self._freshness_score(job)
        quality = _clamp(job.quality.overall)

        overall = 100.0 * (
            self._w.weight_similarity * similarity
            + self._w.weight_skill * skill
            + self._w.weight_experience * experience
            + self._w.weight_location * location
            + self._w.weight_company_priority * company
            + self._w.weight_freshness * freshness
            + self._w.weight_quality * quality
        )
        explanations = self._explain(
            similarity, gap, experience, location, company, freshness, quality
        )
        return MatchDetail(
            score=round(overall, 2),
            similarity=round(similarity, 4),
            skill=round(skill, 4),
            experience=round(experience, 4),
            location=round(location, 4),
            company_priority=round(company, 4),
            freshness=round(freshness, 4),
            quality=round(quality, 4),
            explanations=explanations,
            narrative=self._narrative(round(overall, 2), gap, similarity),
            matched_skills=gap.matched,
            missing_skills=gap.missing,
            resume_id=context.resume_id,
        )

    # ---- component scores ----------------------------------------------
    def _experience_score(self, job: Job, max_years: float) -> float:
        min_years = job.experience.min_years
        if min_years is None:
            return 0.7  # unknown → mildly favourable, not penalised hard
        if min_years <= max_years:
            return 1.0
        return max(0.0, 1.0 - (min_years - max_years) / 5.0)

    def _location_score(self, job: Job, context: ResumeContext) -> float:
        if job.location.is_remote or "remote" in job.location_tags:
            return 1.0
        if not context.preferred_locations:
            return 0.6
        wanted = {loc.lower() for loc in context.preferred_locations}
        fields = (job.location.city, job.location.country, *job.location_tags)
        have = {v.lower() for v in fields if v}
        return 1.0 if wanted & have else 0.2

    def _freshness_score(self, job: Job) -> float:
        if job.posted_date is None:
            return 0.5
        posted = job.posted_date if job.posted_date.tzinfo else job.posted_date.replace(tzinfo=UTC)
        age_hours = (self._now() - posted).total_seconds() / 3600.0
        if age_hours <= 24.0:
            return 1.0
        return max(0.0, 1.0 - age_hours / _FRESH_HORIZON_HOURS)

    # ---- explainability -------------------------------------------------
    def _explain(
        self,
        similarity: float,
        gap: SkillGap,
        experience: float,
        location: float,
        company: float,
        freshness: float,
        quality: float,
    ) -> dict[str, str]:
        matched = ", ".join(gap.matched[:4]) or "none"
        missing = ", ".join(gap.missing[:4]) or "none"
        return {
            "semantic": f"Semantic match {similarity * 100:.0f}% (resume vs job similarity)",
            "skill": (
                f"Skill match {gap.coverage * 100:.0f}% — strong: {matched}; missing: {missing}"
            ),
            "experience": f"Experience fit {experience * 100:.0f}% vs your target range",
            "location": f"Location fit {location * 100:.0f}%",
            "company_priority": f"Company priority {company * 100:.0f}%",
            "freshness": f"Freshness {freshness * 100:.0f}% (recency of posting)",
            "quality": f"Posting quality {quality * 100:.0f}% (completeness & parse confidence)",
        }

    def _narrative(self, score: float, gap: SkillGap, similarity: float) -> str:
        """One-line natural-language summary of the overall match."""

        band = (
            "Excellent match" if score >= 85
            else "Strong match" if score >= 70
            else "Moderate match" if score >= 50
            else "Weak match"
        )
        matched = ", ".join(gap.matched[:3]) or "no overlapping skills yet"
        gap_note = (
            f" Close the gap by learning {', '.join(gap.recommended[:3])}."
            if gap.recommended
            else ""
        )
        return (
            f"{band} ({score:.0f}/100): {similarity * 100:.0f}% semantic similarity, "
            f"strengths in {matched}.{gap_note}"
        )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
