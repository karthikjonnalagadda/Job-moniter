"""Deterministic merge of MNC Excel rows into the existing company datasets.

Pure data transforms (no file IO here) so they are unit-testable in isolation:

* ``MasterIndex`` / ``RuntimeIndex`` - match an ``MncRow`` against existing
  records by normalised name, alias (via ``AliasResolver``), and registrable
  domain.
* ``merge_master`` - enrich existing 25-field master records in place (blank-fill
  only) and return the list of genuinely-new records to append.
* ``merge_runtime`` - return metadata-seed records for MNCs not already present
  in the runtime seed, so they become first-class pipeline sources.

The CLI (``scripts/import_mnc_excel.py``) handles reading/writing files and
calls into these functions.
"""

from __future__ import annotations

from typing import Any

from app.importers.aliases import AliasResolver
from app.importers.mnc_excel import (
    MncRow,
    enrich_master_record,
    master_record,
    metadata_record,
    normalize_name,
    registrable_domain,
)


def _resolver_norm(resolver: AliasResolver, name: str) -> str | None:
    """Canonical normalised name for ``name`` via the alias map, if any."""

    match = resolver.resolve(name)
    return normalize_name(match[1]) if match else None


class _BaseIndex:
    """Common name/alias/domain matching over a list of records."""

    def __init__(
        self,
        records: list[dict[str, Any]],
        resolver: AliasResolver,
        *,
        name_key: str,
        url_keys: tuple[str, ...],
        alias_key: str | None = None,
    ) -> None:
        self._resolver = resolver
        self._by_name: dict[str, dict[str, Any]] = {}
        self._by_domain: dict[str, dict[str, Any]] = {}
        for rec in records:
            name = str(rec.get(name_key) or "")
            if not name:
                continue
            self._by_name.setdefault(normalize_name(name), rec)
            canon = _resolver_norm(resolver, name)
            if canon:
                self._by_name.setdefault(canon, rec)
            if alias_key:
                for alias in rec.get(alias_key) or []:
                    self._by_name.setdefault(normalize_name(str(alias)), rec)
            for url_key in url_keys:
                domain = registrable_domain(str(rec.get(url_key) or ""))
                if domain:
                    self._by_domain.setdefault(domain, rec)

    def match(self, row: MncRow) -> dict[str, Any] | None:
        rec = self._by_name.get(row.norm_name)
        if rec is not None:
            return rec
        canon = _resolver_norm(self._resolver, row.company)
        if canon and (rec := self._by_name.get(canon)) is not None:
            return rec
        if row.domain and (rec := self._by_domain.get(row.domain)) is not None:
            return rec
        return None


class MasterIndex(_BaseIndex):
    """Index over the published 25-field master (``indian_companies.*``)."""

    def __init__(self, records: list[dict[str, Any]], resolver: AliasResolver) -> None:
        super().__init__(
            records, resolver, name_key="company_name", url_keys=("career_url", "website")
        )


class RuntimeIndex(_BaseIndex):
    """Index over the runtime seed (``indian_company_metadata.yaml``)."""

    def __init__(self, records: list[dict[str, Any]], resolver: AliasResolver) -> None:
        super().__init__(
            records,
            resolver,
            name_key="name",
            url_keys=("career_url",),
            alias_key="aliases",
        )


class _IncrementalMatcher:
    """Deduplicates newly-accepted rows against each other (name/alias/domain).

    The Excel itself can list one company under two names (``ADM`` and ``Archer
    Daniels Midland`` share ``adm.com``); the in-file slug dedup misses that, so
    accepted rows are also matched against previously-accepted ones here.
    """

    def __init__(self, resolver: AliasResolver) -> None:
        self._resolver = resolver
        self._by_name: dict[str, dict[str, Any]] = {}
        self._by_domain: dict[str, dict[str, Any]] = {}

    def _keys(self, row: MncRow) -> set[str]:
        keys = {row.norm_name}
        canon = _resolver_norm(self._resolver, row.company)
        if canon:
            keys.add(canon)
        return keys

    def find(self, row: MncRow) -> dict[str, Any] | None:
        for key in self._keys(row):
            if key in self._by_name:
                return self._by_name[key]
        if row.domain and row.domain in self._by_domain:
            return self._by_domain[row.domain]
        return None

    def add(self, row: MncRow, record: dict[str, Any]) -> None:
        for key in self._keys(row):
            self._by_name.setdefault(key, record)
        if row.domain:
            self._by_domain.setdefault(row.domain, record)


def merge_master(
    master: list[dict[str, Any]],
    rows: list[MncRow],
    resolver: AliasResolver,
    today: str,
) -> tuple[list[dict[str, Any]], int, int]:
    """Enrich matches in place; return (new_records, enriched_count, matched_count).

    A single existing record is enriched at most once even if several Excel rows
    map to it (all such rows count as duplicates/matches).
    """

    index = MasterIndex(master, resolver)
    incoming = _IncrementalMatcher(resolver)
    new_records: list[dict[str, Any]] = []
    enriched_ids: set[int] = set()
    matched = 0
    for row in rows:
        existing = index.match(row)
        if existing is not None:
            matched += 1
            if id(existing) not in enriched_ids:
                enrich_master_record(existing, row, today)
                enriched_ids.add(id(existing))
            continue
        if incoming.find(row) is not None:  # same company, second Excel spelling
            matched += 1
            continue
        record = master_record(row, today)
        new_records.append(record)
        incoming.add(row, record)
    return new_records, len(enriched_ids), matched


def merge_runtime(
    runtime: list[dict[str, Any]],
    rows: list[MncRow],
    resolver: AliasResolver,
) -> list[dict[str, Any]]:
    """Return metadata records for MNCs not already in the runtime seed."""

    index = RuntimeIndex(runtime, resolver)
    incoming = _IncrementalMatcher(resolver)
    additions: list[dict[str, Any]] = []
    for row in rows:
        if index.match(row) is not None or incoming.find(row) is not None:
            continue
        record = metadata_record(row)
        additions.append(record)
        incoming.add(row, record)
    return additions
