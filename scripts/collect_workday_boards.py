"""Collect real jobs from discovered Workday boards through the EXISTING pipeline.

Proves the Workday MNCs are not merely catalogued but collectible: for every
master record that carries resolved Workday coordinates (``ats_tenant`` +
``ats_board``) it

1. builds a ``CollectorTarget`` with ``extra={host, tenant, site}`` and runs the
   real, registered ``WorkdayCollector`` against the public CXS API;
2. feeds the collected ``RawJob``s into the real ``JobProcessingPipeline``
   (Normalize -> Filter -> Deduplicate -> Embed -> Rank -> Quality -> Report) —
   the same pipeline the daily run uses. No parallel pipeline is created.

Run:  python -m scripts.collect_workday_boards            # all resolved boards
      python -m scripts.collect_workday_boards --limit 15 # cap the fan-out
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime

from app.api.deps import build_container
from app.collectors.base import CollectorTarget, RawJob
from app.collectors.loader import discover_collectors
from app.collectors.registry import get_collector_class
from app.config.logging import get_logger
from app.config.settings import get_settings
from app.core.quality import QualityScorer
from app.core.ranking.engine import RankingEngine, ResumeContext
from app.core.text import slugify
from app.http.client import RateLimitedHttpClient
from app.models.enums import SourceType
from app.pipeline.factory import build_filter_chain
from app.pipeline.pipeline import JobProcessingPipeline, ProcessItem
from app.routing.workday import parse_workday_url

from scripts.import_mnc_excel import MASTER_JSON, load_master

log = get_logger("scheduler")

_RESUME = (
    "Entry-level AI/ML and Data engineer. Skills: Python, PyTorch, TensorFlow, "
    "SQL, pandas, NLP, LLMs, data engineering, AWS. 0-2 years experience. Seeking "
    "AI Engineer, ML Engineer, Data Scientist, Data Engineer, Data Analyst roles."
)


def workday_targets(master: list[dict], limit: int | None) -> list[tuple[dict, CollectorTarget]]:
    """Master records with resolved Workday coordinates -> collector targets."""

    out: list[tuple[dict, CollectorTarget]] = []
    for rec in sorted(master, key=lambda r: str(r.get("company_name", "")).lower()):
        if str(rec.get("ats_platform") or "").strip().lower() != "workday":
            continue
        tenant = str(rec.get("ats_tenant") or "").strip()
        board = str(rec.get("ats_board") or "").strip()
        url = str(rec.get("discovered_ats_url") or "")
        coords = parse_workday_url(url)
        if not (tenant and board and coords):
            continue
        out.append(
            (
                rec,
                CollectorTarget(
                    company_slug=slugify(str(rec["company_name"])),
                    company_name=str(rec["company_name"]),
                    board_token=tenant,
                    url=str(rec.get("career_url") or ""),
                    extra=coords.to_extra(),
                ),
            )
        )
        if limit and len(out) >= limit:
            break
    return out


async def collect_boards(
    targets: list[tuple[dict, CollectorTarget]],
) -> tuple[list[RawJob], list[tuple[str, int]]]:
    """Drive the real WorkdayCollector over each target (bounded, best-effort)."""

    # A one-off validation over public CXS boards: give the shared client enough
    # throughput that a large board (Workday tenants routinely expose 1-3k
    # openings, paged 20 at a time) completes within the per-board budget instead
    # of starving on the default 2 rps global bucket. Still bounded and polite.
    http_settings = get_settings().http.model_copy(
        update={"default_rate_limit_rps": 10.0, "timeout_seconds": 25.0}
    )
    http = RateLimitedHttpClient(http_settings, max_concurrency=8)
    collector = get_collector_class("workday")(http)  # type: ignore[call-arg]
    all_jobs: list[RawJob] = []
    per_board: list[tuple[str, int]] = []
    sem = asyncio.Semaphore(6)

    async def _one(rec: dict, target: CollectorTarget) -> None:
        async with sem:
            name = str(rec["company_name"])
            try:
                jobs = await asyncio.wait_for(collector.search(target), timeout=120)
            except Exception as exc:
                log.warning("Workday collect failed for {}: {}", name, exc)
                per_board.append((name, -1))
                return
            per_board.append((name, len(jobs)))
            all_jobs.extend(jobs)

    try:
        await asyncio.gather(*(_one(rec, t) for rec, t in targets))
    finally:
        await http.aclose()
    per_board.sort(key=lambda x: x[0].lower())
    return all_jobs, per_board


async def _run(limit: int | None) -> None:
    settings = get_settings()
    discover_collectors()
    container = build_container(settings)

    master = load_master(MASTER_JSON)
    targets = workday_targets(master, limit)
    print(f"\nResolved Workday boards to collect: {len(targets)}")
    for rec, t in targets:
        print(f"  {str(rec['company_name'])[:32]:32s} {t.extra['tenant']:16s} / {t.extra['site']}")

    # --- 1. Real collection through the registered WorkdayCollector ---
    print("\n=== Live Workday collection (real CXS API) ===")
    jobs, per_board = await collect_boards(targets)
    ok_boards = [(n, c) for n, c in per_board if c > 0]
    err_boards = [(n, c) for n, c in per_board if c < 0]
    empty_boards = [(n, c) for n, c in per_board if c == 0]
    for name, count in per_board:
        status = "ERROR" if count < 0 else count
        print(f"  {name[:38]:38s} {status} jobs")
    print(f"\n  boards producing real jobs : {len(ok_boards)}")
    print(f"  boards empty (0 postings)  : {len(empty_boards)}")
    print(f"  boards erroring            : {len(err_boards)}")
    print(f"  TOTAL real jobs collected  : {len(jobs)}")

    if not jobs:
        print("\n  (no jobs collected — network/boards unavailable this run)")
        return

    # --- 2. Feed the REAL pipeline (same one the daily run uses) ---
    resume = ResumeContext(
        resume_id="workday-validation",
        embedding=container.embedder.embed_query(_RESUME),
        skills=["python", "machine learning", "sql", "data engineering", "nlp"],
        preferred_locations=["india", "bengaluru", "remote"],
        max_experience_years=2.0,
    )
    pipeline = JobProcessingPipeline(
        normalizer=container.normalizer,
        filter_chain=build_filter_chain(settings),
        embedder=container.embedder,
        ranker=RankingEngine(settings.ranking),
        quality=QualityScorer(),
        aliases=container.aliases,
        jobs=None,
        runs=None,
    )
    now = datetime.now(tz=UTC)
    items = [
        ProcessItem(
            raw=RawJob(
                external_id=j.external_id,
                title=j.title,
                company=j.company,
                url=j.url or "https://example.com",
                location=j.location,
                description=j.description,
                posted_at=j.posted_at or now,
            ),
            source="workday",
            source_type=SourceType.ATS,
            career_url=j.url,
        )
        for j in jobs
    ]
    result = await pipeline.process(items, resume=resume, persist=False)
    run = result.run
    print("\n=== Existing pipeline funnel over real Workday jobs ===")
    print(f"  collected     : {run.collected}")
    print(f"  normalized    : {run.normalized}")
    print(f"  kept (filter) : {run.normalized - run.filtered_out}")
    print(f"  filtered_out  : {run.filtered_out}")
    print(f"  ranked        : {run.ranked}")
    top = sorted(result.jobs, key=lambda j: (j.match.score if j.match else 0), reverse=True)[:10]
    print("\n=== Top-ranked real Workday jobs ===")
    for j in top:
        score = round(j.match.score, 1) if j.match else 0
        print(f"  {score:5}  {j.company_name[:26]:26s} {j.role[:44]}")

    print(
        "\nRESULT:",
        "PASS" if len(ok_boards) >= 10 else f"CHECK ({len(ok_boards)} boards produced jobs)",
    )


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Collect real jobs from discovered Workday boards.")
    ap.add_argument("--limit", type=int, default=None, help="cap the number of boards")
    args = ap.parse_args()
    asyncio.run(_run(args.limit))


if __name__ == "__main__":
    main()
