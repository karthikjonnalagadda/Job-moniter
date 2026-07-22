"""Skill-gap analysis — compare a resume's skills to a job's requirements.

Returns matched skills, missing skills, a recommended-to-learn subset, and a
learning-priority ordering. Priority weights favour concrete technical skills
(which are usually the gating requirement) over soft skills.
"""

from __future__ import annotations

from pydantic import Field

from app.models.base import AppBaseModel


class LearningItem(AppBaseModel):
    skill: str
    priority: float  # 0-1, higher = learn sooner
    estimated_impact: float = 0.0  # projected coverage lift if acquired (0-1)
    resources: list[str] = Field(default_factory=list)  # placeholder learning resources


def _resources_for(skill: str) -> list[str]:
    """Placeholder learning resources for a skill (wired to a real catalog later)."""

    return [
        f"Official {skill} documentation",
        f"Hands-on {skill} course",
        f"Build a small project using {skill}",
    ]


class SkillGap(AppBaseModel):
    """Result of comparing resume skills against a job's skills."""

    matched: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    recommended: list[str] = Field(default_factory=list)
    learning_priority: list[LearningItem] = Field(default_factory=list)
    coverage: float = 0.0  # matched / required, in [0, 1]


class SkillGapAnalyzer:
    """Compute the gap between a resume and a job posting's skills."""

    def __init__(self, *, recommend_top_n: int = 5) -> None:
        self._top_n = recommend_top_n

    def analyze(
        self,
        resume_skills: list[str],
        job_skills: list[str],
        *,
        job_technologies: list[str] | None = None,
    ) -> SkillGap:
        resume_set = {s.lower(): s for s in resume_skills}
        tech_set = {t.lower() for t in (job_technologies or [])}

        matched: list[str] = []
        missing: list[str] = []
        for skill in job_skills:
            if skill.lower() in resume_set:
                matched.append(skill)
            else:
                missing.append(skill)
        # Technical skills first in the displayed lists (technical skills dominate).
        matched.sort(key=lambda s: s.lower() not in tech_set)
        missing.sort(key=lambda s: s.lower() not in tech_set)

        required = len(job_skills)
        per_skill_lift = (1.0 / required) if required else 0.0
        priority = [
            LearningItem(
                skill=s,
                priority=1.0 if s.lower() in tech_set else 0.6,
                estimated_impact=round(
                    per_skill_lift * (1.0 if s.lower() in tech_set else 0.6), 4
                ),
                resources=_resources_for(s),
            )
            for s in missing
        ]
        # Learning order: highest priority first, then largest coverage impact.
        priority.sort(key=lambda item: (-item.priority, -item.estimated_impact))

        # Coverage is computed over TECHNICAL requirements only — soft skills
        # ("Communication", "Teamwork", "Mentoring") must not dilute a technical
        # match. When a posting lists no technical skills, coverage is unknowable
        # from skills alone → a neutral 0.5 (the semantic component judges fit).
        tech_required = [s for s in job_skills if s.lower() in tech_set]
        if tech_required:
            # Genuine technical requirements: coverage is matched / required
            # (0.0 when the resume covers none of them — a real gap).
            tech_matched = sum(1 for s in tech_required if s.lower() in resume_set)
            coverage = tech_matched / len(tech_required)
        else:
            # No technical requirements could be extracted (sparse posting or
            # soft-skills-only). Skill fit is unknowable from skills alone, so
            # stay neutral (0.5) and let the semantic component judge — do not
            # penalise a relevant posting for a thin description.
            coverage = 0.5

        return SkillGap(
            matched=matched,
            missing=missing,
            recommended=[item.skill for item in priority[: self._top_n]],
            learning_priority=priority,
            coverage=round(coverage, 4),
        )
