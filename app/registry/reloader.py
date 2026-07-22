"""Automatic source-registry hot-reload.

Watches the YAML source file's mtime and reloads the registry when it changes,
so edits to ``ats_sources.yaml`` take effect without restarting the app. Runs as
a background asyncio task started in the app lifespan when
``JOBAGENT_REGISTRY_RELOAD_SECONDS > 0``.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

from app.config.logging import get_logger
from app.registry.loaders import YamlSourceLoader

if TYPE_CHECKING:
    from app.registry.service import SourceRegistry

log = get_logger("registry")


class RegistryReloader:
    """Periodically reloads the registry from a YAML file when it changes."""

    def __init__(self, registry: SourceRegistry, path: Path, interval_seconds: float) -> None:
        self._registry = registry
        self._path = path
        self._interval = interval_seconds
        self._last_mtime: float | None = None
        self._task: asyncio.Task[None] | None = None

    def _current_mtime(self) -> float | None:
        try:
            return self._path.stat().st_mtime
        except OSError:
            return None

    async def maybe_reload(self) -> bool:
        """Reload if the file changed since last check. Returns True if reloaded."""

        mtime = self._current_mtime()
        if mtime is None or mtime == self._last_mtime:
            return False
        first = self._last_mtime is None
        self._last_mtime = mtime
        if first:
            return False  # baseline; initial load handled at startup
        try:
            await self._registry.reload_from(YamlSourceLoader(self._path))
            log.info("Source registry hot-reloaded from {}", self._path.name)
            return True
        except Exception as exc:  # a bad edit must not kill the watcher
            log.error("Registry hot-reload failed (keeping previous): {}", exc)
            return False

    async def _run(self) -> None:
        self._last_mtime = self._current_mtime()  # establish baseline
        while True:
            await asyncio.sleep(self._interval)
            await self.maybe_reload()

    def start(self) -> None:
        if self._interval > 0 and self._task is None:
            self._task = asyncio.create_task(self._run())
            log.info("Registry hot-reload watcher started ({}s interval)", self._interval)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
