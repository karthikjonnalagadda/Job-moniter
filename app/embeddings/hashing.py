"""Dependency-light embedding provider (feature hashing).

Implements the ``EmbeddingProvider`` port with a deterministic hashing-trick
encoder: tokens are hashed into a fixed-dimensional vector (signed), then L2
normalised. It needs only numpy — no model download — so the whole ranking
pipeline runs and is testable now.

It is a genuine bag-of-words embedding: lexically similar texts get high cosine
similarity, which is enough to exercise and validate every downstream stage. The
production ``BAAI/bge-small-en-v1.5`` encoder ships in Phase 9 behind this same
port (a config swap, per the approved architecture — see ADR-001) and requires
the optional ``ml`` dependency group. Dimensionality matches
``settings.vector.dimensions`` (384) so the two are drop-in interchangeable.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

import numpy as np

from app.embeddings.provider import EmbeddingProvider

_TOKEN = re.compile(r"[a-z0-9+#.]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class HashingEmbeddingProvider(EmbeddingProvider):
    """Feature-hashing text embedding (deterministic, numpy-only)."""

    def __init__(self, *, dimensions: int = 384, query_instruction: str = "") -> None:
        self.dimensions = dimensions
        self._query_instruction = query_instruction

    def _encode(self, text: str) -> list[float]:
        vector = np.zeros(self.dimensions, dtype=np.float32)
        tokens = _tokens(text)
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = float(np.linalg.norm(vector))
        if norm > 0.0:
            vector /= norm
        return vector.tolist()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._encode(text or "") for text in texts]

    def embed_query(self, text: str) -> list[float]:
        # bge models prepend a query instruction; mirrored here for parity.
        return self._encode(f"{self._query_instruction}{text or ''}")
