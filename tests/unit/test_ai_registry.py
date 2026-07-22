"""Phase-8 model registry + catalog."""

from __future__ import annotations

from app.ai.catalog import CATALOG, known_models, spec_for
from app.ai.registry import DownloadStatus, ModelRegistry


def test_catalog_has_supported_models() -> None:
    names = {m.name for m in known_models()}
    assert "BAAI/bge-small-en-v1.5" in names
    assert "BAAI/bge-base-en-v1.5" in names
    assert "intfloat/e5-base-v2" in names
    assert "sentence-transformers/all-MiniLM-L6-v2" in names
    assert CATALOG["BAAI/bge-small-en-v1.5"].dimensions == 384
    assert CATALOG["BAAI/bge-base-en-v1.5"].dimensions == 768


def test_spec_for_unknown_synthesises_default() -> None:
    spec = spec_for("acme/custom-model", default_dimensions=512)
    assert spec.name == "acme/custom-model"
    assert spec.dimensions == 512
    assert spec.query_instruction == ""


def test_registry_seeds_catalog() -> None:
    reg = ModelRegistry()
    listed = {r.name for r in reg.list()}
    assert "BAAI/bge-small-en-v1.5" in listed
    assert all(r.catalogued for r in reg.list())


def test_registry_register_name_and_active() -> None:
    reg = ModelRegistry()
    reg.register_name("hashing", dimensions=384, active=True)
    active = reg.active()
    assert active is not None and active.name == "hashing"
    assert reg.get("hashing") is not None


def test_registry_records_inference_average() -> None:
    reg = ModelRegistry()
    reg.register_name("hashing", dimensions=384, active=True)
    reg.record_inference("hashing", count=2, elapsed_ms=20.0)
    reg.record_inference("hashing", count=2, elapsed_ms=40.0)
    rec = reg.get("hashing")
    assert rec is not None
    assert rec.embedding_count == 4
    # total 60ms over 4 items → 15ms/item average
    assert rec.avg_inference_ms == 15.0
    assert rec.last_inference_ms == 20.0  # 40ms / 2 items


def test_registry_status_mutations() -> None:
    reg = ModelRegistry()
    reg.register_name("hashing", dimensions=384, active=True)
    reg.set_download_status("hashing", DownloadStatus.DOWNLOADED)
    reg.set_loaded("hashing", loaded=True)
    reg.set_health("hashing", healthy=True)
    reg.set_memory("hashing", 12.5)
    rec = reg.get("hashing")
    assert rec is not None
    assert rec.download_status is DownloadStatus.DOWNLOADED
    assert rec.loaded and rec.healthy and rec.memory_mb == 12.5


def test_registry_ignores_unknown_mutations() -> None:
    reg = ModelRegistry()
    reg.set_loaded("nonexistent", loaded=True)  # must not raise
    assert reg.get("nonexistent") is None
