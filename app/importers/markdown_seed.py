"""Parser for the seed career-site list (``Indian_Company_Career_Sites.md``).

The seed is a human-curated two-column table (Company | Careers) rendered as a
Pandoc-style grid/ASCII table. This module extracts ``(name, career_url)`` pairs
from it so they can be enriched and emitted as structured CSV/JSON/YAML/Mongo.

The parser is deliberately format-tolerant: it accepts the Pandoc grid layout in
the seed file today, and also plain Markdown pipe tables — so re-exporting the
seed in a different Markdown flavour will not break the pipeline.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from app.core.exceptions import ValidationError

# A run of 2+ spaces separates the two columns in the Pandoc grid layout.
_COLUMN_GAP = re.compile(r"\s{2,}")
_URL = re.compile(r"https?://\S+")


@dataclass(frozen=True)
class SeedEntry:
    name: str
    career_url: str


def _clean_url(url: str) -> str:
    return url.strip().rstrip(".,;")


def _looks_like_rule_or_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if set(stripped) <= {"-", "+", "=", "|", " "}:  # table rule line
        return True
    lowered = stripped.lower()
    return lowered.startswith(("company", "> ", "#")) or lowered == "careers"


def parse_seed_table(path: Path) -> list[SeedEntry]:
    """Parse the seed table into ``SeedEntry`` rows (name + career URL)."""

    if not path.exists():
        raise ValidationError(f"Seed file not found: {path}")
    text = path.read_text(encoding="utf-8")
    return list(_iter_entries(text))


def _iter_entries(text: str) -> Iterator[SeedEntry]:
    seen: set[str] = set()
    for line in text.splitlines():
        if _looks_like_rule_or_header(line):
            continue
        url_match = _URL.search(line)
        if not url_match:
            continue
        career_url = _clean_url(url_match.group(0))
        # Everything before the URL is the company name (grid or pipe table).
        prefix = line[: url_match.start()]
        name = prefix.replace("|", " ").strip()
        # Fall back to splitting on the column gap if the name still has noise.
        if _COLUMN_GAP.search(name):
            name = _COLUMN_GAP.split(name)[0].strip()
        name = name.strip("| ").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        yield SeedEntry(name=name, career_url=career_url)
