"""Ranking: similarity, embeddings, numpy scorer, skill gap, composite engine."""

from __future__ import annotations

from datetime import UTC, datetime

from app.config.settings import RankingSettings
from app.core.ranking.engine import RankingEngine, ResumeContext
from app.core.ranking.skill_gap import SkillGapAnalyzer
from app.core.similarity import cosine, jaccard
from app.embeddings.hashing import HashingEmbeddingProvider
from app.models.common import ExperienceRequirement, Location
from app.models.job import Job
from app.vector.numpy_scorer import NumpyCosineScorer

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _job(**kw: object) -> Job:
    base: dict[str, object] = {
        "job_hash": "h", "external_id": "1", "source": "greenhouse",
        "company_name": "Acme", "role": "ML Engineer", "url": "https://x/1",
    }
    base.update(kw)
    return Job(**base)  # type: ignore[arg-type]


def test_similarity_helpers() -> None:
    assert cosine([1, 0], [1, 0]) == 1.0
    assert cosine([1, 0], [0, 1]) == 0.0
    assert cosine([], [1]) == 0.0
    assert jaccard({"a", "b"}, {"b", "c"}) == 1 / 3
    assert jaccard(set(), {"a"}) == 0.0


def test_hashing_embedding_is_deterministic_and_normalised() -> None:
    p = HashingEmbeddingProvider(dimensions=384)
    v1 = p.embed_query("python fastapi")
    v2 = p.embed_query("python fastapi")
    assert v1 == v2 and len(v1) == 384
    # similar texts are closer than dissimilar ones
    doc_same = p.embed_documents(["python fastapi backend"])[0]
    doc_diff = p.embed_documents(["marketing sales copywriting"])[0]
    assert cosine(v1, doc_same) > cosine(v1, doc_diff)


async def test_numpy_cosine_scorer_ranks() -> None:
    scorer = NumpyCosineScorer([("a", [1.0, 0.0]), ("b", [0.0, 1.0]), ("c", [0.9, 0.1])])
    results = await scorer.search([1.0, 0.0], limit=2)
    assert [r.job_id for r in results] == ["a", "c"]
    assert await NumpyCosineScorer().search([1.0], limit=1) == []


def test_skill_gap() -> None:
    gap = SkillGapAnalyzer().analyze(
        ["Python", "FastAPI"], ["Python", "FastAPI", "Docker", "Kubernetes"],
        # all four are technical (as the real extractor would report them)
        job_technologies=["Python", "FastAPI", "Docker", "Kubernetes"],
    )
    assert set(gap.matched) == {"Python", "FastAPI"}
    assert set(gap.missing) == {"Docker", "Kubernetes"}
    # coverage over technical requirements: 2 of 4 matched
    assert gap.coverage == 0.5
    # technical missing skills rank above non-technical
    assert gap.learning_priority[0].priority == 1.0


def test_ranking_engine_composite_and_explanations() -> None:
    engine = RankingEngine(RankingSettings(), now=lambda: _NOW)
    job = _job(
        skills=["Python", "FastAPI", "RAG"],
        technologies=["Python", "FastAPI", "RAG"],
        embedding=[1.0, 0.0, 0.0],
        experience=ExperienceRequirement(min_years=1),
        location=Location(is_remote=True),
        posted_date=_NOW,
    )
    context = ResumeContext(
        resume_id="ai", skills=["Python", "FastAPI", "RAG"], embedding=[1.0, 0.0, 0.0],
        max_experience_years=2,
    )
    match = engine.rank(job, context, company_priority=0.8)
    assert match.similarity == 1.0
    assert match.skill == 1.0
    assert match.experience == 1.0
    assert match.location == 1.0
    assert match.freshness == 1.0
    assert match.score > 90  # strong match on every axis
    assert match.resume_id == "ai"
    assert "Semantic match" in match.explanations["semantic"]
    assert set(match.matched_skills) == {"Python", "FastAPI", "RAG"}


def test_ranking_penalises_overqualified_and_missing() -> None:
    engine = RankingEngine(RankingSettings(), now=lambda: _NOW)
    job = _job(
        skills=["Java"], technologies=["Java"], experience=ExperienceRequirement(min_years=10)
    )
    context = ResumeContext(skills=["Python"], embedding=None, max_experience_years=2)
    match = engine.rank(job, context)
    assert match.skill == 0.0
    assert match.experience < 1.0  # requires far more than 2 years
    assert "Java" in match.missing_skills
