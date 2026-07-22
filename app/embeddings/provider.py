"""Embedding provider port.

The rest of the application depends on ``EmbeddingProvider`` (the abstraction),
never on sentence-transformers directly. This is what keeps the system
model-agnostic: swapping ``BAAI/bge-small-en-v1.5`` for another model is a
config change, and the query-instruction quirk of bge models is hidden here.

Two concrete providers implement it:
    * ``HashingEmbeddingProvider`` — dependency-light deterministic encoder used
      by CI/tests and as the graceful fallback.
    * ``SentenceTransformerProvider`` — the production model (optional ``ml``
      extra), lazy-loaded behind ``available()``.

Only ``embed_documents`` / ``embed_query`` are abstract. The async, warm-up, and
health-check hooks have safe default implementations so existing providers keep
working and callers can rely on them uniformly (Interface Segregation without
breaking Liskov).
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Sequence


class EmbeddingProvider(ABC):
    """Abstraction over a text-embedding model."""

    #: Vector dimensionality — must match ``settings.vector.dimensions``.
    dimensions: int
    #: Human-readable model identifier for diagnostics / cache keying.
    model_name: str = "hashing"

    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed job descriptions / documents (no query instruction applied)."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a resume / query.

        Implementations apply the model's query instruction prefix here so
        callers stay oblivious to model-specific prompting conventions.
        """

    # ---- optional async surface (default: run the sync path off the loop) ----
    async def aembed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Async document embedding. Heavy providers override to avoid blocking."""

        return await asyncio.to_thread(self.embed_documents, texts)

    async def aembed_query(self, text: str) -> list[float]:
        """Async query embedding."""

        return await asyncio.to_thread(self.embed_query, text)

    # ---- lifecycle hooks ----------------------------------------------------
    async def warmup(self) -> None:  # noqa: B027 - intentional no-op default hook
        """Pay import/model-load cost ahead of first real request (no-op default)."""

    async def health_check(self) -> bool:
        """Return True if the provider can produce an embedding of the right size."""

        try:
            vector = await self.aembed_query("healthcheck")
        except Exception:
            return False
        return len(vector) == self.dimensions
