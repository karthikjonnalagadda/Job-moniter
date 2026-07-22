"""Production embedding provider — ``sentence-transformers`` (optional ``ml`` extra).

Implements the ``EmbeddingProvider`` port with a real transformer encoder
(default ``BAAI/bge-small-en-v1.5``). Everything heavy is **lazy**: the module
imports with no ``torch``/``sentence_transformers`` present, and the model is
only loaded on first use (or explicit ``warmup``). That keeps the lean API image
and CI green while the pipeline/worker image installs the ``ml`` extra.

Features (all behind the same port):
    * configurable model / device / batch size / normalization
    * automatic device selection (CUDA when available, else CPU)
    * batch + memory-aware batching (cap characters per encode call)
    * async support (encode off the event loop)
    * lazy loading with automatic download + optional checksum verification
    * optional int8 dynamic quantization for low-memory CPU hosts
    * model health check + registry/metric hooks (latency, memory, counts)
"""

from __future__ import annotations

import importlib.util
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from app.ai.catalog import spec_for
from app.ai.registry import DownloadStatus, ModelRegistry
from app.config.logging import get_logger
from app.core.exceptions import JobAgentError
from app.embeddings.provider import EmbeddingProvider

if TYPE_CHECKING:
    from app.config.settings import EmbeddingSettings
    from app.metrics.base import MetricsSink

log = get_logger("rank")


class EmbeddingModelUnavailable(JobAgentError):
    """Raised when the production embedding model cannot be loaded."""

    code = "embedding_model_unavailable"
    http_status = 503


class SentenceTransformerProvider(EmbeddingProvider):
    """Real transformer embeddings via ``sentence-transformers`` (lazy-loaded)."""

    def __init__(
        self,
        *,
        model_name: str = "BAAI/bge-small-en-v1.5",
        device: str = "auto",
        dimensions: int = 384,
        batch_size: int = 32,
        max_seq_length: int = 512,
        normalize: bool = True,
        quantize: bool = False,
        download_if_missing: bool = True,
        trust_remote_code: bool = False,
        checksum: str = "",
        max_batch_chars: int = 200_000,
        query_instruction: str | None = None,
        document_instruction: str | None = None,
        registry: ModelRegistry | None = None,
        metrics: MetricsSink | None = None,
    ) -> None:
        spec = spec_for(model_name, default_dimensions=dimensions)
        self.model_name = model_name
        self.dimensions = spec.dimensions or dimensions
        self._configured_device = device
        self._resolved_device: str | None = None
        self._batch_size = max(1, batch_size)
        self._max_seq_length = max_seq_length
        self._normalize = normalize
        self._quantize = quantize
        self._download_if_missing = download_if_missing
        self._trust_remote_code = trust_remote_code
        self._checksum = checksum
        self._max_batch_chars = max_batch_chars
        self._query_instruction = (
            query_instruction if query_instruction is not None else spec.query_instruction
        )
        self._document_instruction = (
            document_instruction
            if document_instruction is not None
            else spec.document_instruction
        )
        self._registry = registry
        self._metrics = metrics
        self._model: Any | None = None
        if registry is not None:
            registry.register(spec, active=True)

    # ---- availability ---------------------------------------------------
    @classmethod
    def available(cls) -> bool:
        """True if the ``ml`` extra (sentence-transformers) is importable."""

        return importlib.util.find_spec("sentence_transformers") is not None

    @classmethod
    def from_settings(
        cls,
        settings: EmbeddingSettings,
        *,
        dimensions: int,
        registry: ModelRegistry | None = None,
        metrics: MetricsSink | None = None,
    ) -> SentenceTransformerProvider:
        return cls(
            model_name=settings.model_name,
            device=str(settings.device),
            dimensions=dimensions,
            batch_size=settings.batch_size,
            max_seq_length=settings.max_seq_length,
            normalize=settings.normalize,
            quantize=settings.quantize,
            download_if_missing=settings.download_if_missing,
            trust_remote_code=settings.trust_remote_code,
            checksum=settings.checksum,
            max_batch_chars=settings.max_batch_chars,
            query_instruction=settings.query_instruction,
            registry=registry,
            metrics=metrics,
        )

    # ---- lazy model loading ---------------------------------------------
    def _resolve_device(self) -> str:
        if self._configured_device in ("cpu", "cuda"):
            return self._configured_device
        # auto: prefer CUDA when torch reports it available.
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except Exception:  # torch missing or broken → CPU
            pass
        return "cpu"

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        if not self.available():
            self._mark(DownloadStatus.MISSING, loaded=False, healthy=False)
            raise EmbeddingModelUnavailable(
                "sentence-transformers is not installed (install the 'ml' extra)",
                details={"model": self.model_name},
            )
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:  # pragma: no cover - import guarded above
            self._mark(DownloadStatus.MISSING, loaded=False, healthy=False)
            raise EmbeddingModelUnavailable(str(exc), details={"model": self.model_name}) from exc

        self._resolved_device = self._resolve_device()
        self._mark(DownloadStatus.DOWNLOADING)
        log.info(
            "Loading embedding model {} on {} (quantize={})",
            self.model_name,
            self._resolved_device,
            self._quantize,
        )
        try:
            model = SentenceTransformer(
                self.model_name,
                device=self._resolved_device,
                trust_remote_code=self._trust_remote_code,
            )
            model.max_seq_length = self._max_seq_length
        except Exception as exc:
            self._mark(DownloadStatus.MISSING, loaded=False, healthy=False)
            raise EmbeddingModelUnavailable(
                f"Failed to load {self.model_name}: {exc}",
                details={"model": self.model_name},
            ) from exc

        self._verify_checksum(model)
        if self._quantize and self._resolved_device == "cpu":
            model = self._apply_quantization(model)
        # Reconcile advertised dimension with the loaded model's true size.
        try:
            reported = model.get_sentence_embedding_dimension()
            if reported:
                self.dimensions = int(reported)
        except Exception:
            pass

        self._model = model
        self._mark(DownloadStatus.DOWNLOADED, loaded=True, healthy=True)
        self._record_memory(model)
        return model

    def _apply_quantization(self, model: Any) -> Any:
        try:
            import torch

            quantized = torch.quantization.quantize_dynamic(
                model, {torch.nn.Linear}, dtype=torch.qint8
            )
            log.info("Applied int8 dynamic quantization to {}", self.model_name)
            return quantized
        except Exception as exc:  # quantization is best-effort
            log.warning("Quantization skipped for {}: {}", self.model_name, exc)
            return model

    def _verify_checksum(self, model: Any) -> None:
        if not self._checksum:
            return
        import hashlib
        from pathlib import Path

        try:
            folder = Path(getattr(model, "_model_card_vars", {}).get("base_model", ""))
            root = folder if folder.exists() else Path(model.tokenizer.name_or_path)
        except Exception:
            log.warning("Checksum requested but model path could not be resolved")
            return
        digest = hashlib.sha256()
        if root.is_dir():
            for file in sorted(root.rglob("*")):
                if file.is_file():
                    digest.update(file.read_bytes())
        actual = digest.hexdigest()
        if actual != self._checksum:
            raise EmbeddingModelUnavailable(
                "Model checksum mismatch — refusing to use a tampered/incorrect model",
                details={"expected": self._checksum, "actual": actual},
            )

    def _record_memory(self, model: Any) -> None:
        if self._registry is None:
            return
        try:
            import torch

            params = sum(
                p.numel() * p.element_size()
                for p in model.parameters()
                if isinstance(p, torch.Tensor)
            )
            self._registry.set_memory(self.model_name, params / (1024 * 1024))
        except Exception:
            pass

    # ---- embedding ------------------------------------------------------
    def _encode(self, texts: list[str], *, is_query: bool) -> list[list[float]]:
        if not texts:
            return []
        model = self._ensure_model()
        prefix = self._query_instruction if is_query else self._document_instruction
        prepared = [f"{prefix}{t or ''}" for t in texts] if prefix else [t or "" for t in texts]
        started = time.perf_counter()
        vectors: list[list[float]] = []
        for batch in self._batches(prepared):
            encoded = model.encode(
                batch,
                batch_size=self._batch_size,
                normalize_embeddings=self._normalize,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            vectors.extend(vec.tolist() for vec in encoded)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self._observe(len(prepared), elapsed_ms, is_query=is_query)
        return vectors

    def _batches(self, texts: list[str]) -> list[list[str]]:
        """Memory-aware batching: cap both count and total characters per call."""

        batches: list[list[str]] = []
        current: list[str] = []
        chars = 0
        for text in texts:
            length = len(text)
            over_count = len(current) >= self._batch_size
            over_chars = self._max_batch_chars and chars + length > self._max_batch_chars
            if current and (over_count or over_chars):
                batches.append(current)
                current, chars = [], 0
            current.append(text)
            chars += length
        if current:
            batches.append(current)
        return batches

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(list(texts), is_query=False)

    def embed_query(self, text: str) -> list[float]:
        result = self._encode([text or ""], is_query=True)
        return result[0] if result else []

    # ---- lifecycle ------------------------------------------------------
    async def warmup(self) -> None:
        import asyncio

        await asyncio.to_thread(self._encode, ["warmup"], is_query=False)
        log.info("Embedding model {} warmed up", self.model_name)

    async def health_check(self) -> bool:
        try:
            vector = await self.aembed_query("healthcheck")
        except Exception as exc:
            log.warning("Embedding health check failed: {}", exc)
            if self._registry is not None:
                self._registry.set_health(self.model_name, False)
            return False
        healthy = len(vector) == self.dimensions
        if self._registry is not None:
            self._registry.set_health(self.model_name, healthy)
        return healthy

    def device_info(self) -> dict[str, object]:
        """Best-effort compute-device report for AI metrics."""

        info: dict[str, object] = {"device": self._resolved_device or self._resolve_device()}
        try:
            import torch

            info["cuda_available"] = bool(torch.cuda.is_available())
            if torch.cuda.is_available():
                info["gpu_name"] = torch.cuda.get_device_name(0)
        except Exception:
            info["cuda_available"] = False
        return info

    # ---- observation helpers -------------------------------------------
    def _observe(self, count: int, elapsed_ms: float, *, is_query: bool) -> None:
        if self._registry is not None:
            self._registry.record_inference(self.model_name, count=count, elapsed_ms=elapsed_ms)
        if self._metrics is not None:
            metric = "ai_embed_query_seconds" if is_query else "ai_embed_documents_seconds"
            self._metrics.observe(metric, elapsed_ms / 1000.0)

    def _mark(
        self,
        status: DownloadStatus,
        *,
        loaded: bool | None = None,
        healthy: bool | None = None,
    ) -> None:
        if self._registry is None:
            return
        self._registry.set_download_status(self.model_name, status)
        if loaded is not None:
            self._registry.set_loaded(self.model_name, loaded)
        if healthy is not None:
            self._registry.set_health(self.model_name, healthy)
