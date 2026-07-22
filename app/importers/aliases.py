"""Company alias resolution.

Maps alternate company names to a canonical identity (e.g. ``Google`` ->
``Alphabet``) so records from different sources deduplicate correctly. Loaded
from ``data/company_aliases.yaml``. Matching is case-insensitive on a normalised
form of the name.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from app.config.logging import get_logger

if TYPE_CHECKING:
    from app.models.company import Company

log = get_logger("import")


def _norm(name: str) -> str:
    return " ".join(name.strip().lower().split())


class AliasResolver:
    """Resolves alternate company names to a canonical (slug, name)."""

    def __init__(self) -> None:
        self._alias_to_canonical: dict[str, tuple[str, str]] = {}

    @classmethod
    def from_file(cls, path: Path) -> AliasResolver:
        resolver = cls()
        if not path.exists():
            log.debug("Alias file {} not present; no aliases loaded", path)
            return resolver
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for slug, entry in data.items():
            canonical_name = (entry or {}).get("canonical_name", slug)
            resolver._alias_to_canonical[_norm(canonical_name)] = (slug, canonical_name)
            for alias in (entry or {}).get("aliases", []):
                resolver._alias_to_canonical[_norm(alias)] = (slug, canonical_name)
        log.info("Loaded {} company aliases", len(resolver._alias_to_canonical))
        return resolver

    def resolve(self, name: str) -> tuple[str, str] | None:
        """Return ``(canonical_slug, canonical_name)`` for ``name``, or None."""

        return self._alias_to_canonical.get(_norm(name))

    def apply(self, company: Company) -> Company:
        """Annotate a company with its canonical identity if it is an alias."""

        match = self.resolve(company.name)
        if match is None:
            return company
        canonical_slug, canonical_name = match
        if canonical_slug != company.slug:
            company.canonical_slug = canonical_slug
            if company.name not in company.aliases:
                company.aliases.append(company.name)
        return company

    def __len__(self) -> int:
        return len(self._alias_to_canonical)
