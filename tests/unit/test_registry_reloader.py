"""Source-registry hot reload (mtime-based)."""

from __future__ import annotations

import os
import time
from pathlib import Path

from app.registry.loaders import YamlSourceLoader
from app.registry.models import SyncState
from app.registry.reloader import RegistryReloader
from app.registry.service import SourceRegistry


async def test_reload_on_file_change(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text("greenhouse: {enabled: true, priority: 2}\n")

    registry = SourceRegistry()
    await registry.load_from(YamlSourceLoader(path))
    assert len(registry) == 1

    reloader = RegistryReloader(registry, path, interval_seconds=0)
    assert await reloader.maybe_reload() is False  # establishes baseline
    assert await reloader.maybe_reload() is False  # unchanged

    # change the file and force a newer mtime
    path.write_text(
        "greenhouse: {enabled: true, priority: 2}\nlever: {enabled: true, priority: 3}\n"
    )
    future = time.time() + 10
    os.utime(path, (future, future))

    assert await reloader.maybe_reload() is True
    assert len(registry) == 2
    assert "lever" in registry


def test_source_definition_has_sync_state_and_limits() -> None:
    from app.registry.models import SourceDefinition

    definition = SourceDefinition(name="greenhouse", rate_limit_rps=3.0)
    assert isinstance(definition.sync_state, SyncState)
    assert definition.sync_state.etag is None
    # falls back to rate_limit_rps when no explicit concurrency block
    limits = definition.limits()
    assert limits.requests_per_second == 3.0
