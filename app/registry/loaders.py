"""Source loaders — read ``SourceDefinition`` records from YAML/JSON/MongoDB.

Each backend is a ``SourceLoader`` adapter behind one interface, so the registry
is agnostic to where sources come from. All loaders coerce their raw records
through ``SourceDefinition`` (Pydantic), which validates types and fills
defaults uniformly.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from app.config.logging import get_logger
from app.core.exceptions import ConfigurationError
from app.registry.models import SourceDefinition

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

log = get_logger("registry")


def _coerce(records: dict[str, dict[str, Any]]) -> list[SourceDefinition]:
    """Turn a ``{name: {fields...}}`` mapping into validated definitions."""

    definitions: list[SourceDefinition] = []
    for name, fields in records.items():
        data = {"name": name, **(fields or {})}
        definitions.append(SourceDefinition.model_validate(data))
    return definitions


class SourceLoader(ABC):
    """Loads source definitions from some backend."""

    #: Loader identifier for diagnostics.
    backend: str = "base"

    @abstractmethod
    async def load(self) -> list[SourceDefinition]:
        """Return all source definitions from this backend."""


class YamlSourceLoader(SourceLoader):
    """Load sources from a YAML file (the default ``ats_sources.yaml``)."""

    backend = "yaml"

    def __init__(self, path: Path) -> None:
        self._path = path

    async def load(self) -> list[SourceDefinition]:
        if not self._path.exists():
            raise ConfigurationError(f"Source file not found: {self._path}")
        raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ConfigurationError(f"Expected a mapping in {self._path}")
        log.info("Loaded {} sources from YAML {}", len(raw), self._path.name)
        return _coerce(raw)


class JsonSourceLoader(SourceLoader):
    """Load sources from a JSON file (mapping or list of objects with ``name``)."""

    backend = "json"

    def __init__(self, path: Path) -> None:
        self._path = path

    async def load(self) -> list[SourceDefinition]:
        if not self._path.exists():
            raise ConfigurationError(f"Source file not found: {self._path}")
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            defs = [SourceDefinition.model_validate(item) for item in raw]
        elif isinstance(raw, dict):
            defs = _coerce(raw)
        else:
            raise ConfigurationError(f"Unsupported JSON shape in {self._path}")
        log.info("Loaded {} sources from JSON {}", len(defs), self._path.name)
        return defs


class MongoSourceLoader(SourceLoader):
    """Load sources from the ``ats_sources`` MongoDB collection."""

    backend = "mongo"

    def __init__(self, db: AsyncIOMotorDatabase, collection: str = "ats_sources") -> None:
        self._db = db
        self._collection = collection

    async def load(self) -> list[SourceDefinition]:
        docs = await self._db[self._collection].find({}).to_list(length=None)
        defs = [
            SourceDefinition.model_validate({k: v for k, v in doc.items() if k != "_id"})
            for doc in docs
        ]
        log.info("Loaded {} sources from Mongo collection '{}'", len(defs), self._collection)
        return defs


def loader_for_path(path: Path) -> SourceLoader:
    """Pick a file loader by extension (``.yaml``/``.yml`` or ``.json``)."""

    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return YamlSourceLoader(path)
    if suffix == ".json":
        return JsonSourceLoader(path)
    raise ConfigurationError(f"Unsupported source file type: {suffix}")
