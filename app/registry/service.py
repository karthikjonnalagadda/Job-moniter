"""SourceRegistry — O(1) source lookup and priority-ordered iteration.

Backed by a plain dict keyed on source name (O(1) get). Populated from one or
more ``SourceLoader`` adapters; later loads override earlier definitions of the
same name (so Mongo can override the YAML baseline). Nothing here runs a
collector — it only answers "what sources exist, are they enabled, and in what
order".
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from app.config.logging import get_logger
from app.models.enums import LegalMode, SourceType
from app.registry.models import SourceDefinition, SourceRegistryStats

if TYPE_CHECKING:
    from app.registry.loaders import SourceLoader

log = get_logger("registry")


class SourceRegistry:
    """In-memory registry of source definitions."""

    def __init__(self) -> None:
        self._sources: dict[str, SourceDefinition] = {}

    # ---- population -----------------------------------------------------
    def add(self, definition: SourceDefinition) -> None:
        self._sources[definition.name] = definition

    async def load_from(self, loader: SourceLoader) -> int:
        """Merge all definitions from ``loader``; returns the count loaded."""

        definitions = await loader.load()
        for definition in definitions:
            self.add(definition)
        log.info("Registry merged {} sources from {} loader", len(definitions), loader.backend)
        return len(definitions)

    def replace_all(self, definitions: list[SourceDefinition]) -> None:
        """Atomically swap the full source set (used by hot-reload)."""

        self._sources = {d.name: d for d in definitions}

    async def reload_from(self, loader: SourceLoader) -> int:
        """Replace the entire registry from ``loader`` (drops removed sources)."""

        definitions = await loader.load()
        self.replace_all(definitions)
        log.info("Registry reloaded: {} sources from {} loader", len(definitions), loader.backend)
        return len(definitions)

    # ---- lookup (O(1)) --------------------------------------------------
    def get(self, name: str) -> SourceDefinition | None:
        return self._sources.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._sources

    def __len__(self) -> int:
        return len(self._sources)

    # ---- queries --------------------------------------------------------
    def all(self) -> list[SourceDefinition]:
        return list(self._sources.values())

    def by_priority(self, *, enabled_only: bool = False) -> list[SourceDefinition]:
        items = self.all()
        if enabled_only:
            items = [s for s in items if s.enabled]
        return sorted(items, key=lambda s: (s.priority, s.name))

    def enabled(self) -> list[SourceDefinition]:
        return self.by_priority(enabled_only=True)

    def by_source_type(self, source_type: SourceType) -> list[SourceDefinition]:
        return [s for s in self.by_priority() if s.source_type == source_type]

    # ---- stats ----------------------------------------------------------
    def stats(self) -> SourceRegistryStats:
        sources = self.all()
        by_type = Counter(str(s.source_type) for s in sources)
        by_legal = Counter(str(s.legal_mode) for s in sources)
        return SourceRegistryStats(
            total=len(sources),
            enabled=sum(1 for s in sources if s.enabled),
            disabled=sum(1 for s in sources if not s.enabled),
            by_source_type=dict(by_type),
            by_legal_mode=dict(by_legal),
            scrape_sources=[s.name for s in sources if s.legal_mode == LegalMode.SCRAPE],
        )
