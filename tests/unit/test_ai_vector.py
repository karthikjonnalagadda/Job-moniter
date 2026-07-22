"""Phase-8 vector search: pipeline builder, numpy paging, Atlas scorer (faked)."""

from __future__ import annotations

from app.vector.atlas_scorer import AtlasVectorScorer, build_search_pipeline
from app.vector.numpy_scorer import NumpyCosineScorer


def test_build_search_pipeline_shape() -> None:
    pipeline = build_search_pipeline(
        [0.1, 0.2],
        index_name="jobs_vector_index",
        path="embedding",
        limit=5,
        num_candidates=100,
        filters={"status": {"$eq": "new"}},
        score_threshold=0.5,
        skip=10,
    )
    stage = pipeline[0]["$vectorSearch"]
    assert stage["index"] == "jobs_vector_index"
    assert stage["path"] == "embedding"
    assert stage["queryVector"] == [0.1, 0.2]
    assert stage["limit"] == 15  # skip + limit
    assert stage["filter"] == {"status": {"$eq": "new"}}
    # numCandidates auto-grows to cover skip+limit
    assert stage["numCandidates"] >= 30
    assert {"$match": {"score": {"$gte": 0.5}}} in pipeline
    assert {"$skip": 10} in pipeline
    assert pipeline[-1] == {"$limit": 5}


def test_build_search_pipeline_minimal() -> None:
    pipeline = build_search_pipeline(
        [1.0], index_name="i", path="embedding", limit=3, num_candidates=50
    )
    assert "filter" not in pipeline[0]["$vectorSearch"]
    assert all("$skip" not in s for s in pipeline)
    assert all("$match" not in s for s in pipeline)


async def test_numpy_scorer_threshold_and_pagination() -> None:
    scorer = NumpyCosineScorer(
        [("a", [1.0, 0.0]), ("b", [0.0, 1.0]), ("c", [0.9, 0.1]), ("d", [0.8, 0.2])]
    )
    # threshold drops the orthogonal "b"
    hits = await scorer.search([1.0, 0.0], limit=10, score_threshold=0.5)
    assert "b" not in [h.job_id for h in hits]
    # pagination: skip the top, take one
    page = await scorer.search([1.0, 0.0], limit=1, skip=1)
    assert len(page) == 1 and page[0].job_id == "c"


class _FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = list(docs)
        self._i = 0

    def __aiter__(self) -> _FakeCursor:
        return self

    async def __anext__(self) -> dict:
        if self._i >= len(self._docs):
            raise StopAsyncIteration
        doc = self._docs[self._i]
        self._i += 1
        return doc


class _FakeCollection:
    def __init__(self, docs: list[dict], indexes: list[dict] | None = None) -> None:
        self._docs = docs
        self._indexes = indexes or []
        self.created: list[dict] = []

    def aggregate(self, pipeline: list[dict]) -> _FakeCursor:
        return _FakeCursor(self._docs)

    def list_search_indexes(self) -> _FakeCursor:
        return _FakeCursor(self._indexes)

    async def create_search_index(self, definition: dict) -> str:
        self.created.append(definition)
        return "idx"


async def test_atlas_scorer_search_maps_results() -> None:
    col = _FakeCollection([{"job_id": "h1", "score": 0.9}, {"job_id": "h2", "score": 0.4}])
    scorer = AtlasVectorScorer(col, index_name="jobs_vector_index")  # type: ignore[arg-type]
    hits = await scorer.search([0.1, 0.2], limit=5)
    assert [(h.job_id, h.similarity) for h in hits] == [("h1", 0.9), ("h2", 0.4)]


async def test_atlas_scorer_empty_query_returns_empty() -> None:
    scorer = AtlasVectorScorer(_FakeCollection([]), index_name="i")  # type: ignore[arg-type]
    assert await scorer.search([], limit=5) == []


async def test_atlas_hybrid_blends_semantic_and_lexical() -> None:
    col = _FakeCollection([{"job_id": "h1", "score": 0.9}, {"job_id": "h2", "score": 0.5}])
    scorer = AtlasVectorScorer(col, index_name="i")  # type: ignore[arg-type]
    hits = await scorer.hybrid_search([0.1], "python engineer", limit=2, alpha=0.6)
    assert {h.job_id for h in hits} == {"h1", "h2"}
    assert all(0.0 <= h.similarity <= 1.0 for h in hits)


async def test_atlas_index_validate_and_bootstrap() -> None:
    missing = _FakeCollection([], indexes=[])
    scorer = AtlasVectorScorer(missing, index_name="jobs_vector_index")  # type: ignore[arg-type]
    assert await scorer.validate_index() is False
    assert await scorer.bootstrap_index() is True
    assert missing.created and missing.created[0]["name"] == "jobs_vector_index"

    present = _FakeCollection([], indexes=[{"name": "jobs_vector_index"}])
    scorer2 = AtlasVectorScorer(present, index_name="jobs_vector_index")  # type: ignore[arg-type]
    assert await scorer2.validate_index() is True
