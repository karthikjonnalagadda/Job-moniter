"""Taxonomy loading + synonym-index construction.

Normalizers (role, location, skill) are all "map many surface forms to one
canonical value" problems. This module loads the YAML taxonomies and builds a
reverse index (synonym → canonical) once, with a small built-in fallback so the
engine works even if a data file is missing (and so unit tests need no files).

Matching is longest-synonym-first to avoid a short synonym (e.g. ``"ai"``)
shadowing a longer, more specific one (e.g. ``"ai engineer"``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.config.logging import get_logger

log = get_logger("normalize")


def load_yaml(path: Path | None) -> Any:
    """Load a YAML file, returning ``None`` if it is absent/unreadable."""

    if path is None or not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        log.warning("Failed to parse taxonomy {}: {}", path, exc)
        return None


class SynonymIndex:
    """A reverse index of ``synonym -> canonical`` with longest-first matching."""

    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self._exact: dict[str, str] = {}
        for canonical, synonyms in mapping.items():
            self._exact[canonical.lower()] = canonical
            for synonym in synonyms:
                self._exact[str(synonym).lower()] = canonical
        # Synonyms sorted longest-first for substring scanning.
        self._by_length = sorted(self._exact.items(), key=lambda kv: -len(kv[0]))

    def __len__(self) -> int:
        return len(self._exact)

    @property
    def canonicals(self) -> set[str]:
        return set(self._exact.values())

    def exact(self, text: str) -> str | None:
        """Return the canonical for an exact (case-insensitive) match."""

        return self._exact.get(text.strip().lower())

    def find_first(self, text: str) -> str | None:
        """Return the canonical of the longest synonym occurring in ``text``."""

        lowered = f" {text.lower()} "
        for synonym, canonical in self._by_length:
            if f" {synonym} " in lowered or synonym in text.lower():
                return canonical
        return None

    def find_all(self, text: str) -> list[str]:
        """Return every canonical whose synonym occurs in ``text`` (deduped)."""

        lowered = text.lower()
        found: list[str] = []
        seen: set[str] = set()
        for synonym, canonical in self._by_length:
            if canonical in seen:
                continue
            if _word_in(synonym, lowered):
                found.append(canonical)
                seen.add(canonical)
        return found


def _word_in(needle: str, haystack: str) -> bool:
    """Whole-token-ish containment (avoids 'go' matching 'category')."""

    idx = haystack.find(needle)
    while idx != -1:
        before = haystack[idx - 1] if idx > 0 else " "
        after_idx = idx + len(needle)
        after = haystack[after_idx] if after_idx < len(haystack) else " "
        if not before.isalnum() and not after.isalnum():
            return True
        idx = haystack.find(needle, idx + 1)
    return False
