"""End-to-end job processing pipeline (mongomock-backed)."""

from __future__ import annotations

from app.collectors.base import RawJob
from app.config.settings import get_settings
from app.core.ranking.engine import ResumeContext
from app.db.repositories.jobs import JobRepository
from app.db.repositories.pipeline_runs import PipelineRunRepository
from app.importers.aliases import AliasResolver
from app.models.enums import ATSType
from app.pipeline.factory import build_pipeline
from app.pipeline.pipeline import ProcessItem


def _item(
    i: int, title: str, company: str, desc: str, loc: str = "Bengaluru, India"
) -> ProcessItem:
    return ProcessItem(
        raw=RawJob(
            external_id=str(i), title=title, company=company,
            url=f"https://boards.greenhouse.io/{company}/jobs/{i}",
            location=loc, description=desc, raw={"posted": "today"},
        ),
        source="greenhouse", ats_type=ATSType.GREENHOUSE, collector_version="1.0.0",
    )


def _build(db):  # type: ignore[no-untyped-def]
    settings = get_settings()
    aliases = AliasResolver.from_file(settings.paths.company_aliases_file)
    return build_pipeline(
        settings, aliases=aliases,
        jobs=JobRepository(db), runs=PipelineRunRepository(db),
    )


async def test_full_pipeline_process(mock_db) -> None:
    pipe = _build(mock_db)
    items = [
        _item(1, "ML Engineer", "Google", "Build RAG with Python, FastAPI, PyTorch. 0-2 years."),
        _item(2, "Machine Learning Engineer", "Alphabet", "Build RAG with Python. 0-2 years."),
        _item(3, "Senior Backend Engineer", "Flipkart", "8+ years Java, Spring, Kubernetes."),
        _item(4, "Data Analyst", "Zomato", "SQL, Python, dashboards. Fresher."),
    ]
    resume = ResumeContext(
        resume_id="ai", skills=["Python", "FastAPI", "PyTorch", "RAG"],
        embedding=pipe.build_resume_context(text="Python FastAPI PyTorch RAG").embedding,
        max_experience_years=2,
    )
    result = await pipe.process(items, resume=resume)

    run = result.run
    assert run.collected == 4
    assert run.filtered_out == 1  # senior backend dropped by seniority-title filter
    assert run.duplicates == 1  # Google/Alphabet folded
    assert run.stored == 2
    assert run.status == "success"
    # per-stage benchmarks recorded
    names = {s.name for s in run.stages}
    assert {"validate", "normalize", "filter", "deduplicate", "embed", "rank", "store"} <= names

    # persisted + ranked, best first
    stored = await JobRepository(mock_db).find({})
    assert len(stored) == 2
    assert result.jobs[0].match is not None
    top, last = result.jobs[0].match, result.jobs[-1].match
    assert top.score >= (last.score if last else 0)

    # run history persisted
    runs = await PipelineRunRepository(mock_db).list_recent()
    assert runs and runs[0].run_id == run.run_id


async def test_incremental_skips_existing(mock_db) -> None:
    pipe = _build(mock_db)
    items = [_item(1, "ML Engineer", "Google", "Python FastAPI. 0-2 years.")]
    first = await pipe.process(items)
    assert first.run.stored == 1
    # second incremental run sees the stored hash and skips it
    second = await pipe.process(items, incremental=True)
    assert second.run.duplicates >= 1
    assert second.run.stored == 0


async def test_resume_only_rerank(mock_db) -> None:
    pipe = _build(mock_db)
    await pipe.process([_item(1, "ML Engineer", "Google", "Python FastAPI RAG. 0-2 years.")])
    resume = pipe.build_resume_context(resume_id="backend", text="Java Spring backend")
    ranked = await pipe.rerank(resume, persist=True)
    assert len(ranked) == 1
    assert ranked[0].match is not None
    assert ranked[0].match.resume_id == "backend"


def test_standalone_dedup_and_skill_extraction(mock_db) -> None:
    pipe = _build(mock_db)
    skills = pipe.extract_skills("Python, FastAPI and Docker on AWS")
    assert "Python" in skills.skills and "AWS" in skills.skills
