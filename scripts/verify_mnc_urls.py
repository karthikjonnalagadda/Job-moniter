"""Live-verify the MNC career URLs flagged ``URL Confidence = Verify``.

Runs a controlled, rate-limited HTTP probe over every master record whose
``url_confidence == "Verify"`` and writes back verification fields. Keeps the
official corporate ``career_url`` untouched; a discovered ATS destination is
stored separately in ``discovered_ats_url`` (never replacing the career URL).

Usage (from repo root; needs network):
    python -m scripts.verify_mnc_urls                 # DRY RUN - probe + report
    python -m scripts.verify_mnc_urls --apply         # write results to master
    python -m scripts.verify_mnc_urls --limit 10      # probe a small sample
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from app.importers.url_verifier import VerifyResult, verify_many

from scripts.import_mnc_excel import MASTER_JSON, load_master, master_columns, write_master

# Verification columns appended to the master schema (stable order).
VERIFY_COLUMNS: tuple[str, ...] = (
    "http_status", "redirect_url", "verified_career_url", "discovered_ats_url",
)
REPORT_JSON = Path("data/companies/sources/mnc_url_verification.json")

_STATUS_TO_CONFIDENCE = {
    "working": "High", "redirected": "High",
    "not_found": "Broken", "invalid": "Broken",
    "blocked": "Verify", "unverified": "Verify",
}


def select_unverified(master: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        r for r in master
        if str(r.get("url_confidence", "")).strip().lower() == "verify"
        and str(r.get("career_url", "")).strip()
    ]


def apply_result(rec: dict[str, Any], res: VerifyResult, today: str) -> None:
    rec["career_status"] = res.career_status
    rec["http_status"] = res.http_status
    rec["redirect_url"] = res.redirect_url
    rec["url_confidence"] = _STATUS_TO_CONFIDENCE.get(res.career_status, "Verify")
    rec["last_verified_date"] = today
    # Keep the official career_url; record the verified landing + any ATS found.
    rec["verified_career_url"] = (
        res.final_url if res.career_status in ("working", "redirected") else ""
    )
    rec["discovered_ats_url"] = res.discovered_ats_url
    # Only fill ATS when we actually detected one AND the record had none.
    if res.ats_platform and str(rec.get("ats_platform", "Unknown")).lower() in ("", "unknown"):
        rec["ats_platform"] = res.ats_platform
        rec["ats_confidence"] = round(res.ats_confidence, 2)
        rec["ats_detection_method"] = "live_probe"
        if res.ats_token and str(rec.get("ats_token", "Unknown")).lower() in ("", "unknown"):
            rec["ats_token"] = res.ats_token


def backfill_tokens(master: list[dict[str, Any]]) -> int:
    """Offline: derive missing ATS tokens from ``discovered_ats_url`` (no network).

    Deterministic and idempotent - only touches records that have a discovered
    ATS URL but still carry an ``Unknown`` token, so a first verification run
    (which predated token capture) can be completed without re-probing sites.
    """

    from app.routing.detector import ATSDetector

    detector = ATSDetector()
    changed = 0
    for rec in master:
        url = str(rec.get("discovered_ats_url") or "")
        if not url:
            continue
        if str(rec.get("ats_token", "Unknown")).lower() not in ("", "unknown"):
            continue
        det = detector.detect(url)
        if det.detected and det.token:
            rec["ats_token"] = det.token
            changed += 1
    return changed


async def _run(limit: int | None, apply: bool, today: str) -> None:
    master = load_master(MASTER_JSON)
    targets = select_unverified(master)
    if limit:
        targets = targets[:limit]
    print(f"Probing {len(targets)} 'Verify' career URLs (concurrency-limited)...")

    items = [(str(r["company_name"]), str(r["career_url"])) for r in targets]
    results = await verify_many(items)

    by_status: Counter[str] = Counter()
    ats_found: Counter[str] = Counter()
    report_rows = []
    for rec, res in zip(targets, results, strict=True):
        by_status[res.career_status] += 1
        if res.ats_platform:
            ats_found[res.ats_platform] += 1
        if apply:
            apply_result(rec, res, today)
        report_rows.append(
            {
                "company": res.company, "input_url": res.input_url,
                "http_status": res.http_status, "career_status": res.career_status,
                "final_url": res.final_url, "redirect_url": res.redirect_url,
                "discovered_ats_url": res.discovered_ats_url,
                "ats": res.ats_platform, "suspicious_redirect": res.suspicious_redirect,
                "error": res.error, "notes": res.notes,
            }
        )

    if apply:
        cols = list(master_columns(master))
        for c in VERIFY_COLUMNS:
            if c not in cols:
                cols.append(c)
        write_master(master, cols)
        REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(
            json.dumps(sorted(report_rows, key=lambda r: r["company"].lower()), indent=2,
                       ensure_ascii=False) + "\n",
            encoding="utf-8", newline="\n",
        )

    _print(by_status, ats_found, len(targets), applied=apply)


def _print(by_status: Counter, ats_found: Counter, total: int, *, applied: bool) -> None:
    print("\n" + "=" * 60)
    print(f"  MNC URL VERIFICATION - {'APPLIED' if applied else 'DRY RUN'}  (n={total})")
    print("=" * 60)
    for status in ("working", "redirected", "unverified", "blocked", "not_found", "invalid"):
        print(f"  {status:12s} {by_status.get(status, 0)}")
    print("  ATS discovered via probe:")
    for ats, n in ats_found.most_common():
        print(f"      {ats:16s} {n}")
    if not ats_found:
        print("      (none)")
    print("=" * 60 + "\n")


def _backfill_only() -> None:
    """Offline token backfill from discovered_ats_url; regenerate master."""

    master = load_master(MASTER_JSON)
    n = backfill_tokens(master)
    cols = list(master_columns(master))
    for c in VERIFY_COLUMNS:
        if c not in cols:
            cols.append(c)
    write_master(master, cols)
    print(f"Backfilled ATS tokens for {n} records (offline, deterministic).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Live-verify MNC career URLs.")
    ap.add_argument("--apply", action="store_true", help="write results to master")
    ap.add_argument("--limit", type=int, default=None, help="probe only the first N")
    ap.add_argument("--today", type=str, default=date.today().isoformat())
    ap.add_argument(
        "--backfill-tokens", action="store_true",
        help="offline: derive missing ATS tokens from discovered_ats_url (no network)",
    )
    args = ap.parse_args()
    if args.backfill_tokens:
        _backfill_only()
        return
    asyncio.run(_run(args.limit, args.apply, args.today))


if __name__ == "__main__":
    main()
