"""Verify company ATS tokens against the real ATS APIs.

The company seed CSV assigns each company an ``ats_platform`` + ``ats_token``.
Many of those were *guessed* (``ats_detection_method == "seed"``) and 404 at
collection time, wasting the daily run's time budget. This script probes every
token against the live ATS endpoint and records whether it actually returns
postings, so the registry can keep only companies that work.

Run:
    python -m scripts.verify_ats_tokens                    # probe + report
    python -m scripts.verify_ats_tokens --write-clean      # also write cleaned CSV

Outputs (next to the input CSV):
    indian_companies.verified.csv  — every row + probe_status + job_count
    indian_companies.clean.csv     — only rows that returned >=1 posting (--write-clean)

No auth is needed for the probed platforms. Workday/Oracle/SuccessFactors/iCIMS
need host/tenant/site (not just a token) and are reported as NEEDS_CONFIG rather
than probed. Teamtailor/JazzHR/BambooHR need an API key and are reported as
NEEDS_AUTH.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
from pathlib import Path

import httpx

CSV_PATH = Path("data/companies/indian_companies.csv")

# Platforms we can probe anonymously, with a (method, url-builder) each.
PROBERS = {
    "greenhouse": (
        "GET",
        lambda t: f"https://boards-api.greenhouse.io/v1/boards/{t}/jobs",
    ),
    "lever": (
        "GET",
        lambda t: f"https://api.lever.co/v0/postings/{t}?mode=json&limit=1",
    ),
    "ashby": ("POST", lambda t: f"https://api.ashbyhq.com/posting-api/job-board/{t}"),
    "recruitee": ("GET", lambda t: f"https://{t}.recruitee.com/api/offers/"),
    "smartrecruiters": (
        "GET",
        lambda t: f"https://api.smartrecruiters.com/v1/companies/{t}/postings?limit=1",
    ),
}
# Real ATS but a token alone is insufficient / needs credentials.
NEEDS_CONFIG = {"workday", "oracle", "successfactors", "icims"}
NEEDS_AUTH = {"teamtailor", "jazzhr", "bamboohr", "comeet", "breezyhr", "jobvite"}


def _job_count(platform: str, payload: object) -> int:
    """Best-effort count of postings in a successful response."""
    if platform == "greenhouse" and isinstance(payload, dict):
        return len(payload.get("jobs", []))
    if platform == "lever" and isinstance(payload, list):
        return len(payload)
    if platform == "ashby" and isinstance(payload, dict):
        return len(payload.get("jobs", []))
    if platform == "recruitee" and isinstance(payload, dict):
        return len(payload.get("offers", []))
    if platform == "smartrecruiters" and isinstance(payload, dict):
        return int(payload.get("totalFound", len(payload.get("content", []))))
    return 0


def probe(row: dict, client: httpx.Client) -> tuple[str, int]:
    platform = (row.get("ats_platform") or "").strip().lower()
    token = (row.get("ats_token") or "").strip()
    if platform in ("", "unknown", "none") or not token or token.lower() == "unknown":
        return "NO_ATS", 0
    if platform in NEEDS_CONFIG:
        return "NEEDS_CONFIG", 0
    if platform in NEEDS_AUTH:
        return "NEEDS_AUTH", 0
    if platform not in PROBERS:
        return f"UNSUPPORTED:{platform}", 0

    method, build = PROBERS[platform]
    url = build(token)
    try:
        resp = client.request(method, url)
    except httpx.HTTPError as exc:
        return f"ERROR:{type(exc).__name__}", 0
    if resp.status_code == 200:
        try:
            n = _job_count(platform, resp.json())
        except ValueError:
            n = 0
        return ("OK" if n else "OK_EMPTY"), n
    return f"HTTP_{resp.status_code}", 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=CSV_PATH)
    ap.add_argument(
        "--write-clean", action="store_true", help="write filtered clean CSV"
    )
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    rows = list(csv.DictReader(args.csv.open(encoding="utf-8")))
    print(f"Loaded {len(rows)} companies from {args.csv}")

    headers = {"User-Agent": "AIJobIntelligenceAgent/verify (+contact via repo)"}
    with (
        httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client,
        cf.ThreadPoolExecutor(max_workers=args.workers) as pool,
    ):
        results = list(pool.map(lambda r: probe(r, client), rows))

    from collections import Counter

    summary: Counter[str] = Counter()
    working = []
    for row, (status, count) in zip(rows, results, strict=True):
        row["probe_status"] = status
        row["job_count"] = count
        summary[status if not status.startswith("HTTP") else "HTTP_ERR"] += 1
        if status in ("OK", "OK_EMPTY"):
            working.append(row)

    out = args.csv.with_suffix(".verified.csv")
    fieldnames = list(rows[0].keys())
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print("\n=== probe summary ===")
    for status, n in summary.most_common():
        print(f"  {status:16} {n}")
    ok = sum(1 for _, (s, _c) in zip(rows, results, strict=True) if s == "OK")
    print(f"\nWorking boards with >=1 live posting: {ok}")
    print(f"Full report -> {out}")

    if args.write_clean:
        clean = args.csv.with_suffix(".clean.csv")
        with clean.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(working)
        print(f"Cleaned CSV ({len(working)} companies) -> {clean}")


if __name__ == "__main__":
    main()
