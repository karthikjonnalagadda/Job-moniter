"""In-memory numpy cosine ``VectorScorer`` (local/dev/test backend).

Ranks a supplied corpus of ``(job_id, embedding)`` by cosine similarity to a
query vector. Used where ``$vectorSearch`` isn't available (local Mongo, CI). The
Atlas backend (Phase 9) implements the same port against the vector index; the
ranking engine depends only on ``VectorScorer`` so the two are interchangeable.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from app.vector.scorer import ScoredJob, VectorScorer


class NumpyCosineScorer(VectorScorer):
    """Cosine ranking over an in-memory embedding corpus."""

    def __init__(self, corpus: Sequence[tuple[str, Sequence[float]]] | None = None) -> None:
        self._ids: list[str] = []
        self._matrix: np.ndarray | None = None
        if corpus:
            self.load(corpus)

    def load(self, corpus: Sequence[tuple[str, Sequence[float]]]) -> None:
        self._ids = [job_id for job_id, _ in corpus]
        if not self._ids:
            self._matrix = None
            return
        matrix = np.asarray([list(vec) for _, vec in corpus], dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        self._matrix = matrix / norms

    async def search(
        self,
        query_vector: Sequence[float],
        *,
        limit: int,
        filters: dict[str, object] | None = None,
        score_threshold: float = 0.0,
        skip: int = 0,
    ) -> list[ScoredJob]:
        if self._matrix is None or not self._ids:
            return []
        query = np.asarray(query_vector, dtype=np.float32)
        norm = np.linalg.norm(query)
        if norm == 0.0:
            return []
        sims = self._matrix @ (query / norm)
        order = np.argsort(-sims)
        scored = [
            ScoredJob(job_id=self._ids[i], similarity=max(0.0, float(sims[i]))) for i in order
        ]
        if score_threshold > 0.0:
            scored = [s for s in scored if s.similarity >= score_threshold]
        return scored[skip : skip + limit]
