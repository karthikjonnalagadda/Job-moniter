"""Prune the company registry to only boards that actually return jobs.

Reads the verified-clean CSV produced by ``scripts.verify_ats_tokens --write-clean``
and, in Mongo, marks those companies ``active_status=True`` and every other company
``active_status=False``. Nothing is deleted — the flag is fully reversible (re-run the
seed importer or flip the flag back to re-activate).

The daily pipeline routes only ``list_active()`` companies, so this stops the run
wasting its time budget on the ~1,380 dead / no-ATS entries.

Usage (needs JOBAGENT_MONGO__URI in the environment / .env):
    python -m scripts.prune_inactive_companies              # DRY RUN — just prints counts
    python -m scripts.prune_inactive_companies --apply      # actually write the flags
    python -m scripts.prune_inactive_companies --apply --clean <path/to/clean.csv>
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from app.config.settings import get_settings
from pymongo import MongoClient

DEFAULT_CLEAN = Path("data/companies/indian_companies.clean.csv")


def load_keep_keys(clean_csv: Path) -> set[tuple[str, str]]:
    """(ats_type, ats_token) pairs, lower-cased, that we want to keep active."""
    keep: set[tuple[str, str]] = set()
    for r in csv.DictReader(clean_csv.open(encoding="utf-8")):
        plat = (r.get("ats_platform") or "").strip().lower()
        tok = (r.get("ats_token") or "").strip().lower()
        if plat and tok and plat not in ("unknown", "none"):
            keep.add((plat, tok))
    return keep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", type=Path, default=DEFAULT_CLEAN)
    ap.add_argument(
        "--apply", action="store_true", help="write changes (default: dry run)"
    )
    args = ap.parse_args()

    settings = get_settings()
    keep = load_keep_keys(args.clean)
    print(f"Keep-list: {len(keep)} verified (ats_type, token) pairs from {args.clean}")

    client: MongoClient = MongoClient(settings.mongo.uri.get_secret_value())
    coll = client[settings.mongo.db_name]["companies"]

    total = coll.count_documents({})
    active_now = coll.count_documents({"active_status": True})
    print(
        f"Mongo '{settings.mongo.db_name}.companies': {total} docs, {active_now} currently active"
    )

    # Compute how many docs match the keep-list (case-insensitive on token + type).
    would_keep = 0
    for plat, tok in keep:
        would_keep += coll.count_documents(
            {
                "ats_type": {"$regex": f"^{plat}$", "$options": "i"},
                "ats_token": {"$regex": f"^{tok}$", "$options": "i"},
            }
        )
    print(
        f"Docs matching keep-list: {would_keep}  →  would deactivate ~{total - would_keep}"
    )

    if not args.apply:
        print("\nDRY RUN — no changes written. Re-run with --apply to commit.")
        return

    # 1) deactivate everything, 2) re-activate the verified keepers.
    coll.update_many({}, {"$set": {"active_status": False}})
    reactivated = 0
    for plat, tok in keep:
        res = coll.update_many(
            {
                "ats_type": {"$regex": f"^{plat}$", "$options": "i"},
                "ats_token": {"$regex": f"^{tok}$", "$options": "i"},
            },
            {"$set": {"active_status": True}},
        )
        reactivated += res.modified_count
    now_active = coll.count_documents({"active_status": True})
    print(
        f"\nApplied. Re-activated {reactivated} docs; {now_active} companies now active."
    )


if __name__ == "__main__":
    main()
