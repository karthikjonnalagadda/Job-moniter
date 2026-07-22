"""Model registry — runtime state for every embedding model in play.

Tracks, per model: name, version, dimensions, download status, loaded status,
health, memory usage, inference latency, and total embeddings produced. This is
the single source of truth behind ``GET /ai/models`` and ``GET /ai/models/health``.

It is a plain in-process singleton-friendly object (constructed once in the DI
container). It records *observations* pushed by providers; it never imports torch
or triggers model loads itself, so it stays cheap and side-effect free.
"""

from __future__ import annotations

import threading
from enum import StrEnum

from app.ai.catalog import ModelSpec, known_models, spec_for
from app.models.base import AppBaseModel


class DownloadStatus(StrEnum):
    UNKNOWN = "unknown"
    MISSING = "missing"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"


class ModelRecord(AppBaseModel):
    """Mutable runtime snapshot of one model."""

    name: str
    version: str = "1"
    dimensions: int
    download_status: DownloadStatus = DownloadStatus.UNKNOWN
    loaded: bool = False
    healthy: bool = False
    memory_mb: float = 0.0
    avg_inference_ms: float = 0.0
    last_inference_ms: float = 0.0
    embedding_count: int = 0
    catalogued: bool = False
    description: str = ""


class ModelRegistry:
    """Thread-safe registry of embedding-model runtime state."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, ModelRecord] = {}
        self._active: str | None = None
        # Pre-seed the catalog so ``/ai/models`` lists supported models even
        # before any of them is loaded.
        for spec in known_models():
            self._records[spec.name] = ModelRecord(
                name=spec.name,
                dimensions=spec.dimensions,
                catalogued=True,
                description=spec.description,
            )

    # ---- registration ---------------------------------------------------
    def register(self, spec: ModelSpec, *, active: bool = False) -> ModelRecord:
        """Ensure a record exists for ``spec``; optionally mark it active."""

        with self._lock:
            record = self._records.get(spec.name)
            if record is None:
                record = ModelRecord(
                    name=spec.name,
                    dimensions=spec.dimensions,
                    catalogued=spec.name in {m.name for m in known_models()},
                    description=spec.description,
                )
                self._records[spec.name] = record
            if active:
                self._active = spec.name
            return record.model_copy()

    def register_name(
        self, model_name: str, *, dimensions: int, active: bool = False
    ) -> ModelRecord:
        """Register by name, resolving the catalog spec (or a synthesised one)."""

        return self.register(
            spec_for(model_name, default_dimensions=dimensions), active=active
        )

    # ---- observations ---------------------------------------------------
    def set_download_status(self, name: str, status: DownloadStatus) -> None:
        self._mutate(name, download_status=status)

    def set_loaded(self, name: str, loaded: bool) -> None:
        self._mutate(name, loaded=loaded)

    def set_health(self, name: str, healthy: bool) -> None:
        self._mutate(name, healthy=healthy)

    def set_memory(self, name: str, memory_mb: float) -> None:
        self._mutate(name, memory_mb=round(memory_mb, 2))

    def record_inference(self, name: str, *, count: int, elapsed_ms: float) -> None:
        """Fold one inference observation into the running average."""

        with self._lock:
            record = self._records.get(name)
            if record is None:
                return
            prev_total = record.avg_inference_ms * record.embedding_count
            record.embedding_count += count
            per_item = elapsed_ms / count if count else elapsed_ms
            record.last_inference_ms = round(per_item, 3)
            if record.embedding_count:
                record.avg_inference_ms = round(
                    (prev_total + elapsed_ms) / record.embedding_count, 3
                )

    # ---- reads ----------------------------------------------------------
    def get(self, name: str) -> ModelRecord | None:
        with self._lock:
            record = self._records.get(name)
            return record.model_copy() if record else None

    def active(self) -> ModelRecord | None:
        with self._lock:
            if self._active is None:
                return None
            record = self._records.get(self._active)
            return record.model_copy() if record else None

    def list(self) -> list[ModelRecord]:
        with self._lock:
            return [r.model_copy() for r in self._records.values()]

    # ---- internal -------------------------------------------------------
    def _mutate(self, name: str, **fields: object) -> None:
        with self._lock:
            record = self._records.get(name)
            if record is None:
                return
            for key, value in fields.items():
                setattr(record, key, value)
