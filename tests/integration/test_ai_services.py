"""Phase-8 AI services: resume/job embeddings, migration, vector search, metrics."""

from __future__ import annotations

from app.ai.job_service import EmbeddingMigrator, JobEmbeddingService
from app.ai.metrics import AiMetricsService
from app.ai.resume_service import ResumeEmbeddingService
from app.ai.search import VectorSearchService
from app.db.repositories.jobs import JobRepository
from app.db.repositories.resume_embeddings import ResumeEmbeddingRepository
from app.embeddings.cache import MemoryEmbeddingCache
from app.embeddings.cached import CachedEmbeddingProvider
from app.embeddings.hashing import HashingEmbeddingProvider
from app.metrics.memory import InMemoryMetrics
from app.models.common import EmbeddingMeta, Location
from app.models.job import Job
from app.vector.numpy_scorer import NumpyCosineScorer


def _embedder(dims: int = 64) -> HashingEmbeddingProvider:
    return HashingEmbeddingProvider(dimensions=dims)


def _job(i: int, role: str = "ML Engineer") -> Job:
    return Job(
        job_hash=f"h{i}", external_id=str(i), source="greenhouse", company_name="Acme",
        role=role, url=f"https://x/{i}", location=Location(city="Bangalore"),
        skills=["Python"], description=f"{role} building things with python",
    )


# ---- resume embeddings ------------------------------------------------------
async def test_resume_embed_skip_and_force(mock_db) -> None:
    repo = ResumeEmbeddingRepository(mock_db)
    service = ResumeEmbeddingService(_embedder(), repo)

    first = await service.embed_resume("backend", "python fastapi mongodb", skills=["Python"])
    assert first.regenerated is True
    assert first.resume.dimensions == 64

    # unchanged content → reuse
    second = await service.embed_resume("backend", "python fastapi mongodb")
    assert second.regenerated is False

    # changed content → regenerate
    changed = await service.embed_resume("backend", "python fastapi kafka")
    assert changed.regenerated is True

    # force always regenerates
    forced = await service.embed_resume("backend", "python fastapi kafka", force=True)
    assert forced.regenerated is True


async def test_resume_is_changed_and_context(mock_db) -> None:
    service = ResumeEmbeddingService(_embedder(), ResumeEmbeddingRepository(mock_db))
    assert await service.is_changed("ai", "text") is True
    result = await service.embed_resume(
        "ai", "text", skills=["Python"], preferred_locations=["Remote"]
    )
    assert await service.is_changed("ai", "text") is False
    ctx = service.to_context(result.resume)
    assert ctx.resume_id == "ai" and ctx.skills == ["Python"] and ctx.embedding is not None


# ---- job embeddings ---------------------------------------------------------
async def test_job_embed_incremental_skip_and_force() -> None:
    service = JobEmbeddingService(_embedder())
    jobs = [_job(1), _job(2)]
    stats = await service.embed_jobs(jobs)
    assert stats.embedded == 2 and stats.skipped == 0
    assert all(j.embedding and j.embedding_meta for j in jobs)

    # second pass: unchanged → all skipped
    stats2 = await service.embed_jobs(jobs)
    assert stats2.embedded == 0 and stats2.skipped == 2

    # force → re-embed
    stats3 = await service.embed_jobs(jobs, force=True)
    assert stats3.embedded == 2


async def test_job_embed_stored_persists(mock_db) -> None:
    repo = JobRepository(mock_db)
    for i in range(3):
        await repo.upsert_by_hash(_job(i))
    service = JobEmbeddingService(_embedder(), jobs=repo)
    stats = await service.embed_stored(only_missing=True)
    assert stats.embedded == 3 and stats.persisted == 3
    stored = await repo.find({}, limit=10)
    assert all(j.embedding is not None for j in stored)


async def test_migrator_reembeds_stale_model(mock_db) -> None:
    repo = JobRepository(mock_db)
    stale = _job(1)
    stale.embedding = [0.0] * 64
    stale.embedding_meta = EmbeddingMeta(model_name="old-model", dimensions=64, content_hash="x")
    await repo.upsert_by_hash(stale)

    service = JobEmbeddingService(_embedder(), jobs=repo)
    report = await EmbeddingMigrator(service, repo).migrate()
    assert report.scanned == 1 and report.migrated == 1
    assert report.from_models.get("old-model") == 1
    migrated = await repo.find_one({"job_hash": "h1"})
    assert migrated is not None and migrated.embedding_meta.model_name == "hashing"


# ---- vector search service --------------------------------------------------
async def test_vector_search_service_hydrates(mock_db) -> None:
    repo = JobRepository(mock_db)
    embedder = _embedder()
    jobs = [_job(1, "Python Engineer"), _job(2, "Java Engineer")]
    await JobEmbeddingService(embedder, jobs=repo).embed_jobs(jobs)
    for job in jobs:
        await repo.upsert_by_hash(job)

    corpus = [(j.job_hash, j.embedding) for j in jobs if j.embedding]
    scorer = NumpyCosineScorer(corpus)
    service = VectorSearchService(embedder, scorer, repo, metrics=InMemoryMetrics())

    results = await service.search(text="python engineer", limit=5)
    assert results.total >= 1
    assert results.hits[0].job is not None  # hydrated
    assert results.took_ms >= 0.0


# ---- ai metrics -------------------------------------------------------------
async def test_ai_metrics_report(mock_db) -> None:
    metrics = InMemoryMetrics()
    cache = MemoryEmbeddingCache()
    embedder = CachedEmbeddingProvider(_embedder(), cache)
    from app.ai.registry import ModelRegistry

    registry = ModelRegistry()
    registry.register_name("hashing", dimensions=64, active=True)

    await embedder.aembed_documents(["a", "b"])
    await embedder.aembed_documents(["a", "b"])  # cache hits
    metrics.observe("ai_vector_search_seconds", 0.05)

    service = AiMetricsService(metrics, cache=cache, registry=registry, embedder=embedder)
    report = await service.build()
    assert report.vector_search_ms == 50.0
    assert report.cache.backend == "memory"
    assert report.cache.hits >= 2
    assert any(m.name == "hashing" for m in report.models)
    assert "device" in report.device
