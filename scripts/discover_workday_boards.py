"""Discover the Workday tenant/site (board) for MNCs detected as Workday.

The ATS detector recognises that a company runs Workday but not *which* tenant
and site the CXS API needs (``https://{host}/wday/cxs/{tenant}/{site}/jobs``).
This script resolves those coordinates and stores them alongside the official
career URL, which is never replaced:

    ats_tenant          first host label   (e.g. "aig")
    ats_board           the Workday "site" (e.g. "External")
    discovered_ats_url  the full board URL

Two phases, both deterministic on their inputs:

1. OFFLINE backfill — for every record that already has a Workday
   ``discovered_ats_url`` (found by a prior URL-verification run), parse the
   tenant + site straight from the URL. No network.
2. LIVE discovery (opt-in, ``--live``) — for records detected as Workday but
   with no board URL yet, politely probe the corporate careers page and read
   the embedded Workday board link out of its HTML.

Usage (from repo root):
    python -m scripts.discover_workday_boards                  # DRY RUN, offline
    python -m scripts.discover_workday_boards --apply          # write offline backfill
    python -m scripts.discover_workday_boards --live --apply   # + live probe
    python -m scripts.discover_workday_boards --live --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

from app.importers.url_verifier import verify_many
from app.routing.workday import is_workday_url, parse_workday_url

from scripts.import_mnc_excel import MASTER_JSON, load_master, master_columns, write_master
from scripts.verify_mnc_urls import VERIFY_COLUMNS

# Coordinate columns appended to the master schema (stable order).
WORKDAY_COLUMNS: tuple[str, ...] = ("ats_tenant", "ats_board")
REPORT_JSON = Path("data/companies/sources/mnc_workday_discovery.json")


def _is_workday_record(rec: dict[str, Any]) -> bool:
    """Detected as Workday, or already carrying a Workday board URL."""

    platform = str(rec.get("ats_platform") or "").strip().lower()
    return platform == "workday" or is_workday_url(str(rec.get("discovered_ats_url") or ""))


def _has_coords(rec: dict[str, Any]) -> bool:
    return bool(
        str(rec.get("ats_tenant") or "").strip() and str(rec.get("ats_board") or "").strip()
    )


def backfill_workday_coords(master: list[dict[str, Any]]) -> int:
    """Offline: derive ats_tenant/ats_board from a Workday ``discovered_ats_url``.

    The board URL is the source of truth, so parsed tenant/site *replace* any
    stored value that disagrees (this repairs coordinates parsed under an older
    rule). Deterministic and idempotent — once reconciled, re-running is a no-op.
    ``ats_token`` is seeded with the tenant only when the record has no real
    token (the collector uses board_token as the tenant fallback).
    """

    resolved = 0
    for rec in master:
        coords = parse_workday_url(str(rec.get("discovered_ats_url") or ""))
        if coords is None:
            continue
        changed = False
        if str(rec.get("ats_tenant") or "").strip() != coords.tenant:
            rec["ats_tenant"] = coords.tenant
            changed = True
        if str(rec.get("ats_board") or "").strip() != coords.site:
            rec["ats_board"] = coords.site
            changed = True
        if str(rec.get("ats_token", "Unknown")).strip().lower() in ("", "unknown", "none"):
            rec["ats_token"] = coords.tenant
            changed = True
        if changed:
            resolved += 1
    return resolved


def select_live_targets(master: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Workday-detected records with no board URL yet and a usable career URL."""

    return [
        r
        for r in master
        if str(r.get("ats_platform") or "").strip().lower() == "workday"
        and not is_workday_url(str(r.get("discovered_ats_url") or ""))
        and str(r.get("career_url") or "").strip()
    ]


async def live_discover(
    master: list[dict[str, Any]], *, limit: int | None, today: str
) -> tuple[int, list[dict[str, Any]]]:
    """Probe corporate career pages for an embedded Workday board (opt-in)."""

    targets = select_live_targets(master)
    if limit:
        targets = targets[:limit]
    if not targets:
        return 0, []

    print(f"Live-probing {len(targets)} Workday career pages for embedded boards…")
    items = [(str(r["company_name"]), str(r["career_url"])) for r in targets]
    results = await verify_many(items)

    found = 0
    report: list[dict[str, Any]] = []
    for rec, res in zip(targets, results, strict=True):
        coords = (
            parse_workday_url(res.discovered_ats_url) if res.ats_platform == "workday" else None
        )
        if coords is not None:
            rec["discovered_ats_url"] = res.discovered_ats_url
            rec["ats_tenant"] = coords.tenant
            rec["ats_board"] = coords.site
            if str(rec.get("ats_token", "Unknown")).strip().lower() in ("", "unknown", "none"):
                rec["ats_token"] = coords.tenant
            rec["last_verified_date"] = today
            found += 1
        report.append(
            {
                "company": res.company,
                "career_url": res.input_url,
                "http_status": res.http_status,
                "career_status": res.career_status,
                "discovered_ats_url": res.discovered_ats_url,
                "ats_tenant": coords.tenant if coords else "",
                "ats_board": coords.site if coords else "",
                "error": res.error,
            }
        )
    return found, report


def _columns(master: list[dict[str, Any]]) -> list[str]:
    cols = list(master_columns(master))
    for group in (VERIFY_COLUMNS, WORKDAY_COLUMNS):
        for col in group:
            if col not in cols:
                cols.append(col)
    return cols


def _report(master: list[dict[str, Any]]) -> None:
    wd = [r for r in master if _is_workday_record(r)]
    with_coords = [r for r in wd if _has_coords(r)]
    print("\n" + "=" * 60)
    print("  WORKDAY BOARD DISCOVERY")
    print("=" * 60)
    print(f"  Workday companies (detected)   : {len(wd)}")
    print(f"  …with tenant + board resolved  : {len(with_coords)}")
    print(f"  …still unresolved              : {len(wd) - len(with_coords)}")
    print("  Sample resolved boards:")
    for r in sorted(with_coords, key=lambda r: str(r.get('company_name', '')).lower())[:12]:
        print(
            f"      {str(r.get('company_name',''))[:30]:30s} "
            f"{r.get('ats_tenant',''):18s} / {r.get('ats_board','')}"
        )
    print("=" * 60 + "\n")


async def _run(*, apply: bool, live: bool, limit: int | None, today: str) -> None:
    master = load_master(MASTER_JSON)

    offline = backfill_workday_coords(master)
    print(f"Offline backfill: resolved coordinates for {offline} record(s).")

    live_found = 0
    live_report: list[dict[str, Any]] = []
    if live:
        live_found, live_report = await live_discover(master, limit=limit, today=today)
        print(f"Live discovery: found {live_found} new Workday board(s).")

    if apply:
        write_master(master, _columns(master))
        if live_report:
            REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
            REPORT_JSON.write_text(
                json.dumps(
                    sorted(live_report, key=lambda r: r["company"].lower()),
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
        print("APPLIED — master datasets regenerated (career_url left untouched).")
    else:
        print("DRY RUN — no files written. Re-run with --apply to commit.")

    _report(master)


def main() -> None:
    ap = argparse.ArgumentParser(description="Discover Workday tenant/site for MNCs.")
    ap.add_argument("--apply", action="store_true", help="write results to master")
    ap.add_argument("--live", action="store_true", help="probe career pages for boards (network)")
    ap.add_argument("--limit", type=int, default=None, help="cap live probes")
    ap.add_argument("--today", type=str, default=date.today().isoformat())
    args = ap.parse_args()
    asyncio.run(_run(apply=args.apply, live=args.live, limit=args.limit, today=args.today))


if __name__ == "__main__":
    main()
