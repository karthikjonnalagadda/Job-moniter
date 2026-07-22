"""Production ``VectorScorer`` — MongoDB Atlas ``$vectorSearch``.

Runs approximate-nearest-neighbour search against the Atlas vector index on
``jobs.embedding`` and returns ``ScoredJob`` rows keyed by ``job_hash``. Same
port as ``NumpyCosineScorer`` (the local/CI backend), so the two are fully
interchangeable — selection is ``settings.vector.backend``.

Capabilities: similarity search, top-k, metadata filters, score threshold,
pagination, and a hybrid (semantic + lexical) mode. Index bootstrap and
validation helpers keep the deployed index in lock-step with app config.

The aggregation is built by the pure ``build_search_pipeline`` function so the
query shape is unit-testable without a live Atlas cluster (``$vectorSearch`` is
unavailable in mongomock).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from app.config.logging import get_logger
from app.vector.scorer import ScoredJob, VectorScorer

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

    from app.config.settings import Settings

log = get_logger("rank")


def build_search_pipeline(
    query_vector: Sequence[float],
    *,
    index_name: str,
    path: str,
    limit: int,
    num_candidates: int,
    filters: dict[str, Any] | None = None,
    score_threshold: float = 0.0,
    skip: int = 0,
) -> list[dict[str, Any]]:
    """Return the ``$vectorSearch`` aggregation pipeline (pure / testable)."""

    vector_stage: dict[str, Any] = {
        "index": index_name,
        "path": path,
        "queryVector": list(query_vector),
        "numCandidates": max(num_candidates, (skip + limit) * 2),
        "limit": skip + limit,
    }
    if filters:
        vector_stage["filter"] = filters

    pipeline: list[dict[str, Any]] = [
        {"$vectorSearch": vector_stage},
        {
            "$project": {
                "_id": 0,
                "job_id": "$job_hash",
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    if score_threshold > 0.0:
        pipeline.append({"$match": {"score": {"$gte": score_threshold}}})
    if skip > 0:
        pipeline.append({"$skip": skip})
    pipeline.append({"$limit": limit})
    return pipeline


class AtlasVectorScorer(VectorScorer):
    """Cosine ranking via Atlas ``$vectorSearch`` over ``jobs.embedding``."""

    def __init__(
        self,
        collection: AsyncIOMotorCollection,
        *,
        index_name: str = "jobs_vector_index",
        path: str = "embedding",
        num_candidates: int = 200,
        dimensions: int = 384,
        similarity: str = "cosine",
    ) -> None:
        self._col = collection
        self._index_name = index_name
        self._path = path
        self._num_candidates = num_candidates
        self._dimensions = dimensions
        self._similarity = similarity

    @classmethod
    def from_settings(cls, db: AsyncIOMotorDatabase, settings: Settings) -> AtlasVectorScorer:
        vec = settings.vector
        return cls(
            db["jobs"],
            index_name=vec.index_name,
            path=vec.path,
            num_candidates=vec.num_candidates,
            dimensions=vec.dimensions,
            similarity=vec.similarity,
        )

    async def search(
        self,
        query_vector: Sequence[float],
        *,
        limit: int,
        filters: dict[str, object] | None = None,
        score_threshold: float = 0.0,
        skip: int = 0,
    ) -> list[ScoredJob]:
        if not query_vector:
            return []
        pipeline = build_search_pipeline(
            query_vector,
            index_name=self._index_name,
            path=self._path,
            limit=limit,
            num_candidates=self._num_candidates,
            filters=dict(filters) if filters else None,
            score_threshold=score_threshold,
            skip=skip,
        )
        results: list[ScoredJob] = []
        try:
            cursor = self._col.aggregate(pipeline)
            async for doc in cursor:
                results.append(
                    ScoredJob(job_id=doc["job_id"], similarity=max(0.0, float(doc["score"])))
                )
        except Exception as exc:  # never let a search error crash a request
            log.error("Atlas vector search failed: {}", exc)
            return []
        return results

    async def hybrid_search(
        self,
        query_vector: Sequence[float],
        text: str,
        *,
        limit: int,
        alpha: float = 0.6,
        filters: dict[str, object] | None = None,
        score_threshold: float = 0.0,
    ) -> list[ScoredJob]:
        """Blend semantic (``$vectorSearch``) and lexical (text index) scores.

        ``alpha`` weights the semantic side; ``1 - alpha`` the lexical side.
        Scores are min-max normalised per source before blending so neither
        dominates by scale. Falls back to pure vector search when no text.
        """

        semantic = await self.search(
            query_vector, limit=limit * 2, filters=filters, score_threshold=score_threshold
        )
        if not text.strip():
            return semantic[:limit]
        lexical = await self._text_search(text, limit=limit * 2, filters=filters)

        blended: dict[str, float] = {}
        for job_id, score in _normalise(semantic).items():
            blended[job_id] = blended.get(job_id, 0.0) + alpha * score
        for job_id, score in _normalise(lexical).items():
            blended[job_id] = blended.get(job_id, 0.0) + (1.0 - alpha) * score
        ranked = sorted(blended.items(), key=lambda kv: -kv[1])[:limit]
        return [ScoredJob(job_id=jid, similarity=round(score, 4)) for jid, score in ranked]

    async def _text_search(
        self, text: str, *, limit: int, filters: dict[str, object] | None
    ) -> list[ScoredJob]:
        query: dict[str, Any] = {"$text": {"$search": text}}
        if filters:
            query.update(filters)
        pipeline: list[dict[str, Any]] = [
            {"$match": query},
            {"$project": {"_id": 0, "job_id": "$job_hash", "score": {"$meta": "textScore"}}},
            {"$sort": {"score": -1}},
            {"$limit": limit},
        ]
        out: list[ScoredJob] = []
        try:
            async for doc in self._col.aggregate(pipeline):
                out.append(ScoredJob(job_id=doc["job_id"], similarity=float(doc.get("score", 0.0))))
        except Exception as exc:
            log.warning("Lexical search leg failed: {}", exc)
        return out

    # ---- index lifecycle ------------------------------------------------
    def index_definition(self) -> dict[str, Any]:
        """The Atlas ``vectorSearch`` index this scorer expects."""

        return {
            "name": self._index_name,
            "type": "vectorSearch",
            "definition": {
                "fields": [
                    {
                        "type": "vector",
                        "path": self._path,
                        "numDimensions": self._dimensions,
                        "similarity": self._similarity,
                    },
                    {"type": "filter", "path": "status"},
                    {"type": "filter", "path": "work_mode"},
                    {"type": "filter", "path": "location_tags"},
                ]
            },
        }

    async def bootstrap_index(self) -> bool:
        """Create the vector search index if missing. Idempotent; best-effort."""

        try:
            existing = await self.validate_index()
            if existing:
                return True
            await self._col.create_search_index(self.index_definition())
            log.info("Requested Atlas vector index '{}' (build is async)", self._index_name)
            return True
        except Exception as exc:  # shared-tier / mongomock / offline → non-fatal
            log.warning("Vector index bootstrap skipped: {}", exc)
            return False

    async def validate_index(self) -> bool:
        """True if the expected vector search index exists on the collection."""

        try:
            async for idx in self._col.list_search_indexes():
                if idx.get("name") == self._index_name:
                    return True
        except Exception as exc:
            log.debug("Vector index validation unavailable: {}", exc)
        return False


def _normalise(scored: list[ScoredJob]) -> dict[str, float]:
    """Min-max normalise similarities into [0, 1], keyed by job_id."""

    if not scored:
        return {}
    values = [s.similarity for s in scored]
    lo, hi = min(values), max(values)
    span = hi - lo
    if span == 0.0:
        return {s.job_id: 1.0 for s in scored}
    return {s.job_id: (s.similarity - lo) / span for s in scored}
