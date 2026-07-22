"""Phase-8 ranking extensions: quality factor, narrative, skill-gap intelligence."""

from __future__ import annotations

from datetime import UTC, datetime

from app.config.settings import RankingSettings
from app.core.ranking.engine import RankingEngine, ResumeContext
from app.core.ranking.skill_gap import SkillGapAnalyzer
from app.models.common import ExperienceRequirement, Location, QualityScore
from app.models.job import Job

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _job(**kw: object) -> Job:
    base: dict[str, object] = {
        "job_hash": "h", "external_id": "1", "source": "greenhouse",
        "company_name": "Acme", "role": "ML Engineer", "url": "https://x/1",
    }
    base.update(kw)
    return Job(**base)  # type: ignore[arg-type]


def test_default_weights_include_quality_zero_and_narrative() -> None:
    engine = RankingEngine(RankingSettings(), now=lambda: _NOW)
    job = _job(skills=["Python"], embedding=[1.0, 0.0], quality=QualityScore(overall=0.5))
    ctx = ResumeContext(skills=["Python"], embedding=[1.0, 0.0])
    match = engine.rank(job, ctx)
    # quality is reported even though its weight is 0 by default
    assert match.quality == 0.5
    assert "quality" in match.explanations
    assert match.narrative  # non-empty natural-language summary


def test_quality_weight_shifts_score() -> None:
    weights = RankingSettings(
        weight_similarity=0.35,
        weight_skill=0.20,
        weight_experience=0.15,
        weight_location=0.10,
        weight_company_priority=0.10,
        weight_freshness=0.05,
        weight_quality=0.05,
    )
    engine = RankingEngine(weights, now=lambda: _NOW)
    ctx = ResumeContext(skills=["Python"], embedding=[1.0, 0.0], max_experience_years=2)
    high_q = engine.rank(
        _job(skills=["Python"], embedding=[1.0, 0.0], quality=QualityScore(overall=1.0),
             experience=ExperienceRequirement(min_years=1), location=Location(is_remote=True),
             posted_date=_NOW),
        ctx,
    )
    low_q = engine.rank(
        _job(skills=["Python"], embedding=[1.0, 0.0], quality=QualityScore(overall=0.0),
             experience=ExperienceRequirement(min_years=1), location=Location(is_remote=True),
             posted_date=_NOW),
        ctx,
    )
    assert high_q.score > low_q.score  # quality now contributes


def test_skill_gap_has_impact_and_resources() -> None:
    gap = SkillGapAnalyzer().analyze(
        ["Python"], ["Python", "Docker", "Kubernetes", "Communication"],
        job_technologies=["Docker", "Kubernetes"],
    )
    top = gap.learning_priority[0]
    assert top.priority == 1.0  # technical skill first
    assert top.estimated_impact > 0.0
    assert top.resources  # placeholder resources present
    # non-technical skill ranks below technical
    comm = next(i for i in gap.learning_priority if i.skill == "Communication")
    assert comm.priority < 1.0
    assert gap.recommended  # a recommended-to-learn subset exists
