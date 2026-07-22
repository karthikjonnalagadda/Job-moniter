"""Source registry: the single source of truth for which job sources exist.

Sources are declared as data (YAML / JSON / MongoDB), never hardcoded. The
``SourceRegistry`` loads them through pluggable ``SourceLoader`` adapters and
offers O(1) lookup plus priority-ordered iteration. It is deliberately separate
from the *collector* registry: this describes *what* sources exist and their
enablement/priority; the collector registry provides the *code* that runs them.
"""

from app.registry.loaders import (
    JsonSourceLoader,
    MongoSourceLoader,
    SourceLoader,
    YamlSourceLoader,
    loader_for_path,
)
from app.registry.models import (
    ConcurrencyLimits,
    SourceDefinition,
    SourceRegistryStats,
    SyncState,
)
from app.registry.service import SourceRegistry

__all__ = [
    "ConcurrencyLimits",
    "JsonSourceLoader",
    "MongoSourceLoader",
    "SourceDefinition",
    "SourceLoader",
    "SourceRegistry",
    "SourceRegistryStats",
    "SyncState",
    "YamlSourceLoader",
    "loader_for_path",
]
