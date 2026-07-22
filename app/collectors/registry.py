"""Collector plugin registry.

Collectors register themselves with ``@register("name")``. The pipeline asks
the registry for enabled collectors — enablement and priority come from
``data/ats_sources.yaml`` (loaded in Phase 4), never from hardcoded lists.

Adding a new source = create one module with a ``@register(...)`` class. No core
code changes. That is the plugin promise from Phase 1/2.
"""

from __future__ import annotations

from collections.abc import Callable

from app.collectors.base import BaseCollector, CollectorMetadata
from app.config.logging import get_logger
from app.core.exceptions import ConfigurationError

log = get_logger("collectors")

_REGISTRY: dict[str, type[BaseCollector]] = {}


def register(name: str) -> Callable[[type[BaseCollector]], type[BaseCollector]]:
    """Class decorator that adds a collector to the registry under ``name``."""

    def decorator(cls: type[BaseCollector]) -> type[BaseCollector]:
        key = name.lower()
        if key in _REGISTRY:
            raise ConfigurationError(f"Collector '{key}' already registered")
        cls.name = key
        _REGISTRY[key] = cls
        log.debug("Registered collector '{}'", key)
        return cls

    return decorator


def get_collector_class(name: str) -> type[BaseCollector]:
    try:
        return _REGISTRY[name.lower()]
    except KeyError as exc:
        raise ConfigurationError(f"No collector registered as '{name}'") from exc


def available_collectors() -> dict[str, type[BaseCollector]]:
    """Return a copy of the registry (name -> class)."""

    return dict(_REGISTRY)


def describe_all() -> list[CollectorMetadata]:
    """Return capability metadata for every registered collector, priority-sorted."""

    metas = [cls.describe() for cls in _REGISTRY.values()]
    return sorted(metas, key=lambda m: (m.priority, m.name))
