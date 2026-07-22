"""File parsers for company imports.

Yields raw ``(row_number, record)`` pairs so the validator/service can report
issues by source position. CSV is streamed row-by-row (constant memory, suitable
for 100k+ rows); JSON/YAML are structured documents loaded whole (they are
list/mapping shaped by nature).

Accepted shapes:
    * CSV  — header row + data rows.
    * JSON — a list of objects, or a ``{slug: {..}}`` mapping, or ``{"companies": [...]}``.
    * YAML — the same shapes as JSON.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

from app.core.exceptions import ValidationError

RawRecord = dict[str, Any]


def _records_from_structured(data: Any) -> list[RawRecord]:
    """Normalise a parsed JSON/YAML document into a list of record dicts."""

    if isinstance(data, dict) and "companies" in data:
        data = data["companies"]
    if isinstance(data, list):
        return [dict(item) for item in data]
    if isinstance(data, dict):
        # {slug: {fields}} mapping — inject the slug key.
        records: list[RawRecord] = []
        for key, value in data.items():
            record = dict(value) if isinstance(value, dict) else {}
            record.setdefault("slug", key)
            records.append(record)
        return records
    raise ValidationError("Unsupported document shape for company import")


def parse_records(path: Path) -> Iterator[tuple[int, RawRecord]]:
    """Yield ``(row_number, raw_record)`` for each company in ``path``.

    ``row_number`` is 1-based and, for CSV, corresponds to the data row
    (excluding the header).
    """

    if not path.exists():
        raise ValidationError(f"Import file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader, start=1):
                # Drop the CSV's None key (extra columns) and blank-out empties.
                cleaned = {k: v for k, v in row.items() if k is not None}
                yield index, cleaned
    elif suffix in {".json"}:
        data = json.loads(path.read_text(encoding="utf-8"))
        for index, record in enumerate(_records_from_structured(data), start=1):
            yield index, record
    elif suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for index, record in enumerate(_records_from_structured(data), start=1):
            yield index, record
    else:
        raise ValidationError(f"Unsupported import file type: {suffix}")


def detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    return {".csv": "csv", ".json": "json", ".yaml": "yaml", ".yml": "yaml"}.get(suffix, "unknown")
