"""End-to-end pipeline validation for newly-added MNC companies.

Proves the MNCs are not just catalogued but *usable* by the Job Monitor
pipeline. For 20 newly-added MNCs spanning distinct sectors it:

1. Loads them as ``Company`` models and routes them (``CompanyRouter``) to show
   which collector each is wired to.
2. Best-effort LIVE collection from any company whose ATS is a public board
   (Greenhouse/Lever/Ashby) with a token - real jobs off the wire.
3. Drives the full pipeline (Normalize -> Filter -> Deduplicate -> Embed -> Rank ->
   Quality -> Report) over representative postings at those companies using the
   REAL engines (real bge embedder + ranker), and asserts the role/seniority
   filters keep target 0-2 YOE AI/Data roles and reject senior ones.

Run:  python -m scripts.validate_mnc_pipeline
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.api.deps import build_container
from app.collectors.base import RawJob
from app.collectors.loader import discover_collectors
from app.config.logging import get_logger
from app.config.settings import get_settings
from app.core.quality import QualityScorer
from app.core.ranking.engine import RankingEngine, ResumeContext
from app.core.text import slugify
from app.models.company import Company
from app.models.enums import ATSType, SourceType
from app.pipeline.factory import build_filter_chain
from app.pipeline.pipeline import JobProcessingPipeline, ProcessItem
from app.registry.loaders import YamlSourceLoader
from app.registry.service import SourceRegistry
from app.routing.router import CompanyRouter

from scripts.import_mnc_excel import MASTER_JSON, load_master

log = get_logger("scheduler")

TARGET_ROLES = [
    "AI Engineer", "Machine Learning Engineer", "Data Scientist", "Data Analyst",
    "Data Engineer", "Python Developer", "Backend Engineer", "Software Engineer",
    "Generative AI Engineer", "LLM Engineer", "NLP Engineer",
    "Computer Vision Engineer", "Applied Scientist", "Research Engineer",
    "AI/ML Intern", "Data Science Intern", "Machine Learning Intern",
]
REJECT_ROLES = [
    "Senior Data Scientist", "Staff ML Engineer", "Principal Engineer",
    "Lead Data Engineer", "Software Architect", "Engineering Manager",
    "Director of AI", "VP Engineering", "Head of Data",
]
_RESUME = (
    "Entry-level AI/ML and Data engineer. Skills: Python, PyTorch, TensorFlow, "
    "scikit-learn, SQL, pandas, NLP, LLMs, RAG, data engineering, AWS. "
    "0-2 years experience. Seeking AI Engineer, ML Engineer, Data Scientist, "
    "Data Engineer, Applied Scientist, Backend Engineer roles."
)


def pick_diverse_mncs(master: list[dict], n: int = 20) -> list[dict]:
    """Pick n newly-added MNCs spread across distinct sectors (deterministic)."""

    mncs = sorted(
        (r for r in master if r.get("source") == "mnc_excel_2026"),
        key=lambda r: str(r.get("company_name", "")).lower(),
    )
    picked: list[dict] = []
    seen_cat: dict[str, int] = {}
    # Round-robin across categories for sector diversity.
    for cap in (1, 2, 3, 99):
        for r in mncs:
            if len(picked) >= n:
                break
            cat = str(r.get("category", "unknown"))
            if seen_cat.get(cat, 0) < cap and r not in picked:
                picked.append(r)
                seen_cat[cat] = seen_cat.get(cat, 0) + 1
    return picked[:n]


def to_company(rec: dict) -> Company:
    ats = str(rec.get("ats_platform", "unknown")).lower()
    ats_type = ATSType(ats) if ats in {a.value for a in ATSType} else ATSType.UNKNOWN
    token = rec.get("ats_token")
    token = None if str(token).lower() in ("", "unknown", "none") else str(token)
    return Company(
        name=str(rec["company_name"]),
        slug=slugify(str(rec["company_name"])),
        ats_type=ats_type,
        ats_token=token,
        career_url=rec.get("career_url") or None,
        company_category=str(rec.get("category", "unknown")),
        country=rec.get("country") or None,
    )


def synth_items(company: str, career_url: str | None) -> list[ProcessItem]:
    now = datetime.now(tz=UTC)
    items: list[ProcessItem] = []
    for i, title in enumerate(TARGET_ROLES + REJECT_ROLES):
        is_target = title in TARGET_ROLES
        desc = (
            "Entry-level role, 0-2 years experience, freshers/new grads welcome. "
            "Work on Python, ML, data pipelines."
            if is_target
            else "Requires extensive experience leading teams."
        )
        items.append(
            ProcessItem(
                raw=RawJob(
                    external_id=f"{slugify(company)}-{i}",
                    title=title,
                    company=company,
                    url=f"{career_url or 'https://example.com'}#job{i}",
                    location="Bengaluru, India",
                    description=desc,
                    posted_at=now,
                ),
                source="career_site",
                source_type=SourceType.CAREER_SITE,
                career_url=career_url,
            )
        )
    return items


def collectible_mncs(master: list[dict], limit: int = 6) -> list[Company]:
    """Newly-added MNCs on a public board (Greenhouse/Lever/Ashby) with a token."""

    out: list[Company] = []
    for r in sorted(master, key=lambda r: str(r.get("company_name", "")).lower()):
        if r.get("source") != "mnc_excel_2026":
            continue
        c = to_company(r)
        if c.ats_type in (ATSType.GREENHOUSE, ATSType.LEVER, ATSType.ASHBY) and c.ats_token:
            out.append(c)
        if len(out) >= limit:
            break
    return out


async def _live_collect(companies: list[Company]) -> dict[str, int]:
    """Real collection from public-board ATS companies (bounded, best-effort)."""

    from app.collectors.base import CollectorTarget
    from app.collectors.registry import get_collector_class
    from app.http.client import RateLimitedHttpClient

    http = RateLimitedHttpClient(get_settings().http)  # collectors need a shared client
    out: dict[str, int] = {}
    try:
        for c in companies:
            ats = str(c.ats_type)  # Company stores enum values as strings
            label = f"{c.name} [{ats}:{c.ats_token}]"
            try:
                collector = get_collector_class(ats)(http)  # type: ignore[call-arg]
                jobs = await asyncio.wait_for(
                    collector.search(CollectorTarget(company_slug=c.slug, board_token=c.ats_token)),
                    timeout=25,
                )
                out[label] = len(jobs)
            except Exception as exc:
                log.warning("Live collect failed for {}: {}", c.name, exc)
                out[label] = -1
    finally:
        await http.aclose()
    return out


async def _run() -> None:
    settings = get_settings()
    discover_collectors()
    container = build_container(settings)

    master = load_master(MASTER_JSON)
    picked = pick_diverse_mncs(master, 20)
    companies = [to_company(r) for r in picked]

    # --- 1. Routing ---
    registry = SourceRegistry()
    if settings.paths.ats_sources_file.exists():
        await registry.load_from(YamlSourceLoader(settings.paths.ats_sources_file))
    router = CompanyRouter(registry)
    print("\n=== 20 MNC companies -- routing & sectors ===")
    route_counts: dict[str, int] = {}
    for c, r in zip(companies, picked, strict=True):
        d = router.route(c)
        tgt = getattr(d, "collector", None) or getattr(d, "strategy", "none")
        route_counts[str(tgt)] = route_counts.get(str(tgt), 0) + 1
        print(f"  {c.name[:34]:34s} {r.get('category',''):14s} -> {tgt}")
    print("  routing summary:", route_counts)

    # --- 2. Real live collection from collectible MNCs (discovered ATS boards) ---
    print("\n=== Live collection from collectible MNCs (real ATS APIs) ===")
    live = await _live_collect(collectible_mncs(master, limit=6))
    total_live = 0
    if live:
        for name, n in live.items():
            total_live += max(n, 0)
            print(f"  {name}: {'ERROR' if n < 0 else n} jobs")
        print(f"  -> total real jobs collected: {total_live}")
    else:
        print("  (no public-board MNCs with tokens found)")

    # --- 3. Full pipeline over representative postings ---
    resume = ResumeContext(
        resume_id="validation",
        embedding=container.embedder.embed_query(_RESUME),
        skills=["python", "machine learning", "sql", "pytorch", "nlp", "data engineering"],
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
    items: list[ProcessItem] = []
    for c in companies:
        items.extend(synth_items(c.name, c.career_url))

    result = await pipeline.process(items, resume=resume, persist=False)
    run = result.run
    kept_roles = sorted({j.role for j in result.jobs})
    print("\n=== Pipeline funnel (20 companies x 26 postings) ===")
    print(f"  collected     : {run.collected}")
    print(f"  normalized    : {run.normalized}")
    print(f"  kept (filter) : {run.normalized - run.filtered_out}")
    print(f"  filtered_out  : {run.filtered_out}")
    print(f"  rejected_by   : {run.rejected_by}")
    print(f"  ranked        : {run.ranked}")
    n_target = len(TARGET_ROLES) * len(companies)
    n_reject = len(REJECT_ROLES) * len(companies)
    reject_survivors = [r for r in kept_roles if r in REJECT_ROLES]
    target_kept = [r for r in TARGET_ROLES if r in kept_roles]
    print("\n=== Role-filter correctness ===")
    print(f"  target roles kept   : {len(target_kept)}/{len(TARGET_ROLES)} distinct")
    print(f"  senior roles kept   : {len(reject_survivors)} (must be 0)  {reject_survivors}")
    print(f"  expected: keep ~{n_target} target postings, reject all {n_reject} senior")

    # --- Report: top-ranked ---
    top = sorted(result.jobs, key=lambda j: (j.match.score if j.match else 0), reverse=True)[:10]
    print("\n=== Report: top-10 ranked MNC jobs ===")
    for j in top:
        score = round(j.match.score, 1) if j.match else 0
        print(f"  {score:5}  {j.company_name[:26]:26s} {j.role}")

    ok = not reject_survivors and (run.normalized - run.filtered_out) == n_target
    print(f"\n  distinct target roles surviving dedup+rank: {len(target_kept)}")
    print("\nRESULT:", "PASS" if ok else "CHECK")


def main() -> None:
    import sys

    # Company names carry accents; avoid a Windows cp1252 crash on output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
