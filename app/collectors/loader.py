"""Dynamic collector plugin discovery.

Collectors are auto-discovered by importing every module under the collector
sub-packages (``ats``, ``career_sites``, ``job_boards``). Importing a module runs
its ``@register(...)`` decorator, which populates the registry. Adding a new
source therefore requires only dropping a module into one of those packages — no
manual registration, no central list to edit.

A failing plugin import is isolated and logged (bulkhead) so one broken plugin
never prevents the others from loading.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from app.collectors import ats, career_sites, job_boards
from app.collectors.base import BaseCollector
from app.collectors.registry import available_collectors
from app.config.logging import get_logger

log = get_logger("collectors")

# Packages scanned for collector plugins, in priority-tier order.
_DISCOVERY_PACKAGES: tuple[ModuleType, ...] = (career_sites, ats, job_boards)

_discovered = False


def discover_collectors(*, force: bool = False) -> dict[str, type[BaseCollector]]:
    """Import all plugin modules and return the populated registry.

    Idempotent: the actual import work runs once per process (Python caches
    modules); pass ``force=True`` to re-scan (e.g. after adding a module at
    runtime in tests).
    """

    global _discovered
    if _discovered and not force:
        return available_collectors()

    loaded = 0
    failed = 0
    for package in _DISCOVERY_PACKAGES:
        for module_info in pkgutil.iter_modules(package.__path__, prefix=f"{package.__name__}."):
            short_name = module_info.name.rsplit(".", 1)[-1]
            if short_name.startswith("_"):
                continue  # skip private modules
            try:
                importlib.import_module(module_info.name)
                loaded += 1
            except Exception as exc:  # one bad plugin must not sink the rest
                failed += 1
                log.error("Collector plugin failed to load [{}]: {}", module_info.name, exc)

    _discovered = True
    registry = available_collectors()
    log.info(
        "Collector discovery complete ({} modules scanned, {} failed, {} registered)",
        loaded,
        failed,
        len(registry),
    )
    return registry
