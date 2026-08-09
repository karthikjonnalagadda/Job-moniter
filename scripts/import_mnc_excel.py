"""Import the India MNC career-sites Excel into the company database.

Merges ``India_MNC_Career_Sites_Master_2026.xlsx`` (sheet ``MNC Career Sites``)
into BOTH operative datasets, without a parallel pipeline:

* ``data/companies/indian_company_metadata.yaml`` - the runtime seed. New MNCs
  are appended (preserving the file's existing bytes/comments) so they become
  first-class pipeline sources.
* ``data/companies/indian_companies.{json,yaml,csv}`` - the published master.
  Existing matches are enriched (blank-fill), new companies appended; all three
  formats are regenerated deterministically (sorted by company name).

Usage (from repo root):
    python -m scripts.import_mnc_excel                # DRY RUN - prints the report
    python -m scripts.import_mnc_excel --apply        # write the files
    python -m scripts.import_mnc_excel --excel <path> --today 2026-08-09
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from app.importers.aliases import AliasResolver
from app.importers.mnc_excel import (
    MASTER_NEW_COLUMNS,
    MergeStats,
    MncExcelReader,
    MncRow,
)
from app.importers.mnc_merge import merge_master, merge_runtime

DATA_DIR = Path("data/companies")
DEFAULT_EXCEL = DATA_DIR / "sources" / "India_MNC_Career_Sites_Master_2026.xlsx"
MASTER_JSON = DATA_DIR / "indian_companies.json"
MASTER_YAML = DATA_DIR / "indian_companies.yaml"
MASTER_CSV = DATA_DIR / "indian_companies.csv"
RUNTIME_YAML = DATA_DIR / "indian_company_metadata.yaml"
ALIASES = Path("data/company_aliases.yaml")

_LIST_FIELDS = ("preferred_roles", "preferred_technologies", "tech_stack")


# --------------------------------------------------------------------------
# Loaders
# --------------------------------------------------------------------------
def load_master(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "companies" in data:
        data = data["companies"]
    return [dict(r) for r in data]


def load_runtime(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if isinstance(data, dict) and "companies" in data:
        data = data["companies"]
    return [dict(r) for r in data]


def master_columns(records: list[dict[str, Any]]) -> list[str]:
    """Existing 25-field order (from the first record) + new provenance columns."""

    base = list(records[0].keys()) if records else []
    cols = list(base)
    for col in MASTER_NEW_COLUMNS:
        if col not in cols:
            cols.append(col)
    return cols


# --------------------------------------------------------------------------
# Writers (deterministic, sorted)
# --------------------------------------------------------------------------
def _sorted_master(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda r: str(r.get("company_name", "")).lower())


def _aligned(records: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    """Ensure every record has every column (fill missing with "")."""

    out = []
    for rec in records:
        row = {col: rec.get(col, "") for col in columns}
        out.append(row)
    return out


def write_master(records: list[dict[str, Any]], columns: list[str]) -> None:
    ordered = _aligned(_sorted_master(records), columns)
    # newline="\n" everywhere: keep files LF (repo convention) on Windows too.
    MASTER_JSON.write_text(
        json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    MASTER_YAML.write_text(
        yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
        newline="\n",
    )
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for rec in ordered:
        row = dict(rec)
        for f in _LIST_FIELDS:
            val = row.get(f)
            if isinstance(val, list):
                row[f] = "; ".join(str(x) for x in val)
        writer.writerow(row)
    MASTER_CSV.write_text(buf.getvalue(), encoding="utf-8", newline="\n")


def _yaml_scalar(value: Any) -> str:
    """Emit a value as a YAML scalar.

    Strings are double-quoted (via JSON, a strict YAML subset) whenever a plain
    emit would be unsafe - special characters, surrounding whitespace, OR an
    implicit-type collision where YAML would re-read the text as a non-string
    (e.g. ``NO`` -> bool False, ``null`` -> None, ``12`` -> int). The round-trip
    check is what prevents the classic ``country: NO`` (Norway) footgun.
    """

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    text = str(value)
    unsafe = (
        text == ""
        or text.strip() != text
        or any(c in text for c in ":#{}[]&*!|>'\"%@`,")
    )
    if not unsafe:
        try:
            unsafe = not isinstance(yaml.safe_load(text), str)
        except yaml.YAMLError:
            unsafe = True
    return json.dumps(text, ensure_ascii=False) if unsafe else text


def format_runtime_entry(rec: dict[str, Any]) -> str:
    """Render one metadata-seed record in the file's existing style."""

    order = (
        "name", "slug", "career_url", "industry", "headquarters", "country",
        "company_category", "ats_type", "ats_token", "career_platform",
        "priority_score", "ai_hiring_score", "remote_support", "crawl_frequency",
        "supported_roles", "preferred_technologies", "aliases", "notes",
    )
    lines = [f"- name: {_yaml_scalar(rec['name'])}"]
    for key in order[1:]:
        lines.append(f"  {key}: {_yaml_scalar(rec.get(key))}")
    return "\n".join(lines)


def append_runtime(additions: list[dict[str, Any]], *, tag: str) -> None:
    if not additions:
        return
    additions = sorted(additions, key=lambda r: str(r.get("name", "")).lower())
    existing = RUNTIME_YAML.read_text(encoding="utf-8")
    if not existing.endswith("\n"):
        existing += "\n"
    block = [f"\n# ==================== {tag} ===================="]
    block.extend(format_runtime_entry(rec) for rec in additions)
    RUNTIME_YAML.write_text(existing + "\n".join(block) + "\n", encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------
# Report assembly
# --------------------------------------------------------------------------
def _url_and_ats_stats(rows: list[MncRow], stats: MergeStats) -> None:
    ats: Counter[str] = Counter()
    for row in rows:
        if row.url_verified:
            stats.urls_verified += 1
        elif row.url:
            stats.urls_to_verify += 1
        else:
            stats.urls_malformed += 1
            stats.manual_review.append(f"{row.company}: unusable URL '{row.url_raw}'")
        ats[row.detection.ats_type.value if row.detection.detected else "unknown"] += 1
        # Detected ATS on an unverified URL is worth a human glance.
        if row.detection.detected and not row.url_verified:
            stats.manual_review.append(
                f"{row.company}: ATS '{row.detection.ats_type.value}' detected on "
                f"URL-confidence=Verify ({row.url})"
            )
    stats.ats_breakdown = dict(sorted(ats.items(), key=lambda kv: -kv[1]))


def run(excel: Path, *, today: str, apply: bool) -> MergeStats:
    resolver = AliasResolver.from_file(ALIASES)
    reader = MncExcelReader()
    rows = reader.read(excel)

    master = load_master(MASTER_JSON)
    runtime = load_runtime(RUNTIME_YAML)

    stats = MergeStats(existing_master=len(master), excel_rows=len(rows))
    _url_and_ats_stats(rows, stats)

    new_master, enriched, matched = merge_master(master, rows, resolver, today)
    stats.new_to_master = len(new_master)
    stats.enriched_master = enriched
    stats.duplicates = matched

    additions_runtime = merge_runtime(runtime, rows, resolver)
    stats.new_to_runtime = len(additions_runtime)
    stats.already_runtime = len(rows) - len(additions_runtime)

    if apply:
        combined = master + new_master
        columns = master_columns(master)
        write_master(combined, columns)
        append_runtime(additions_runtime, tag="MNC ADDITIONS (Excel MNC master 2026)")

    _print_report(stats, applied=apply)
    return stats


def _print_report(stats: MergeStats, *, applied: bool) -> None:
    print("\n" + "=" * 68)
    print(f"  MNC EXCEL IMPORT - {'APPLIED' if applied else 'DRY RUN'}")
    print("=" * 68)
    print(f"  Existing master companies      : {stats.existing_master}")
    print(f"  Excel companies (rows)         : {stats.excel_rows}")
    print(f"  New companies added (master)   : {stats.new_to_master}")
    print(f"  Duplicates (matched existing)  : {stats.duplicates}")
    print(f"  Existing records enriched      : {stats.enriched_master}")
    print(f"  New first-class runtime seeds  : {stats.new_to_runtime}")
    print(f"  Already in runtime seed        : {stats.already_runtime}")
    print(f"  URLs verified (High confidence) : {stats.urls_verified}")
    print(f"  URLs requiring verification     : {stats.urls_to_verify}")
    print(f"  URLs malformed/unusable         : {stats.urls_malformed}")
    print(f"  Final master company count      : {stats.master_final}")
    print("  ATS detection breakdown        :")
    for plat, n in stats.ats_breakdown.items():
        print(f"      {plat:16s} {n}")
    if stats.manual_review:
        print(f"  Manual review items            : {len(stats.manual_review)}")
        for item in stats.manual_review[:10]:
            print(f"      - {item}")
        if len(stats.manual_review) > 10:
            print(f"      ... (+{len(stats.manual_review) - 10} more)")
    print("=" * 68 + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Import the India MNC career-sites Excel.")
    ap.add_argument("--excel", type=Path, default=DEFAULT_EXCEL)
    ap.add_argument("--today", type=str, default="2026-08-09")
    ap.add_argument("--apply", action="store_true", help="write files (default: dry run)")
    args = ap.parse_args()
    run(args.excel, today=args.today, apply=args.apply)


if __name__ == "__main__":
    main()
