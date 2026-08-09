"""Mark permanently-dead career URLs inactive (deterministic maintenance pass).

Sets an ``active_status`` flag on every master record from fields already
present — no network. A record is marked inactive only when its career page is a
hard, permanent failure (404/410/invalid) *and* it has no ATS collection path,
so nothing collectible is ever switched off. Where a company has a discovered
ATS board, it stays active and the daily router prefers that ATS over the dead
or WAF-blocked corporate page (the official ``career_url`` is always retained).

Usage (from repo root):
    python -m scripts.mark_dead_urls            # DRY RUN — report only
    python -m scripts.mark_dead_urls --apply    # write active_status to master
"""

from __future__ import annotations

import argparse
from typing import Any

from app.importers.collection_status import (
    compute_active_status,
    has_ats_collection_path,
    is_dead_endpoint,
)

from scripts.discover_workday_boards import WORKDAY_COLUMNS
from scripts.import_mnc_excel import MASTER_JSON, load_master, master_columns, write_master
from scripts.verify_mnc_urls import VERIFY_COLUMNS

ACTIVE_COLUMN = "active_status"


def apply_active_status(master: list[dict[str, Any]]) -> dict[str, int]:
    """Set ``active_status`` on every record; return summary counts."""

    dead_no_ats = dead_with_ats = blocked_with_ats = deactivated = 0
    for rec in master:
        active = compute_active_status(rec)
        rec[ACTIVE_COLUMN] = active
        if not active:
            deactivated += 1
        if is_dead_endpoint(rec):
            if has_ats_collection_path(rec):
                dead_with_ats += 1
            else:
                dead_no_ats += 1
        status = str(rec.get("career_status") or "").strip().lower()
        if status == "blocked" and has_ats_collection_path(rec):
            blocked_with_ats += 1
    return {
        "deactivated": deactivated,
        "dead_no_ats": dead_no_ats,
        "dead_resolved_via_ats": dead_with_ats,
        "waf_resolved_via_ats": blocked_with_ats,
        "ats_collectible": sum(has_ats_collection_path(r) for r in master),
    }


def _columns(master: list[dict[str, Any]]) -> list[str]:
    cols = list(master_columns(master))
    for group in (VERIFY_COLUMNS, WORKDAY_COLUMNS, (ACTIVE_COLUMN,)):
        for col in group:
            if col not in cols:
                cols.append(col)
    return cols


def main() -> None:
    ap = argparse.ArgumentParser(description="Mark permanently-dead career URLs inactive.")
    ap.add_argument("--apply", action="store_true", help="write active_status to master")
    args = ap.parse_args()

    master = load_master(MASTER_JSON)
    stats = apply_active_status(master)

    if args.apply:
        write_master(master, _columns(master))
        print("APPLIED — active_status written to master (career_url untouched).")
    else:
        print("DRY RUN — no files written. Re-run with --apply to commit.")

    print("\n" + "=" * 56)
    print("  DEAD-URL / COLLECTION-SOURCE MARKING")
    print("=" * 56)
    print(f"  Records deactivated (dead, no ATS) : {stats['dead_no_ats']}")
    print(f"  Dead pages resolved via ATS        : {stats['dead_resolved_via_ats']}")
    print(f"  WAF-blocked pages resolved via ATS : {stats['waf_resolved_via_ats']}")
    print(f"  Total ATS-collectible companies    : {stats['ats_collectible']}")
    print("=" * 56 + "\n")


if __name__ == "__main__":
    main()
