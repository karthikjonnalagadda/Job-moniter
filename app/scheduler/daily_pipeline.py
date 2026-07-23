"""Daily production pipeline orchestration.

Composes the existing, individually-tested components into the end-to-end daily
run:

    collect → normalize → filter → dedup → embed → rank → store → report → email

It **reuses** the exact same building blocks the API uses — ``get_pipeline`` and
``get_notification_service`` from ``app.api.deps``, the ``CompanyRouter``,
``CollectorExecutor``, and ``build_priority_map`` — and adds only the
orchestration glue that previously had no home: building the collector work-list
from routed companies, wrapping ``RawJob``s into ``ProcessItem``s, wiring company
priority, an idempotency guard, and an audit record.

No business logic (filtering, ranking, reporting, sending) lives here — only
sequencing, logging, and failure handling. Nothing about the pipeline is
redesigned.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime

from app.api.deps import Container, get_notification_service, get_pipeline
from app.collectors.base import CollectorTarget
from app.collectors.context import CollectorContext
from app.collectors.executor import CollectorExecutor
from app.collectors.loader import discover_collectors
from app.collectors.registry import available_collectors
from app.config.logging import get_logger
from app.config.settings import Settings
from app.core.classification import build_priority_map
from app.db.repositories.benchmarks import BenchmarkRepository
from app.db.repositories.companies import CompanyRepository
from app.db.repositories.runs import RunRepository
from app.models.company import Company
from app.models.enums import ATSType, RunStatus, SourceType
from app.models.report_record import DeliveryStatus, ReportFormat
from app.models.run import SchedulerRun
from app.pipeline.pipeline import ProcessItem
from app.registry.loaders import YamlSourceLoader
from app.routing.models import RoutingConfig
from app.routing.router import CompanyRouter

log = get_logger("scheduler")

WorkList = list[tuple[str, list[CollectorTarget]]]


def _ats_for(collector: str) -> ATSType:
    """Best-effort ATSType for a collector name (ATS collectors == their type)."""

    try:
        return ATSType(collector)
    except ValueError:
        return ATSType.UNKNOWN


def build_work_list(companies: list[Company], router: CompanyRouter) -> WorkList:
    """Route companies to collectors and group them into a per-collector work-list.

    Pure orchestration glue: ``CompanyRouter`` decides which collector services
    each company; we group the routed companies by collector and build one
    ``CollectorTarget`` per company (board token + slug + name).
    """

    by_slug = {c.slug: c for c in companies}
    grouped: dict[str, list[CollectorTarget]] = {}
    for decision in router.route_all(companies).decisions:
        if not decision.routed or not decision.collector:
            continue
        company = by_slug.get(decision.company_slug)
        if company is None:
            continue
        grouped.setdefault(decision.collector, []).append(
            CollectorTarget(
                company_slug=company.slug,
                company_name=company.name,
                board_token=company.ats_token,
                url=company.career_url,
            )
        )
    return [(name, targets) for name, targets in grouped.items() if targets]


def resolve_resume_text(settings: Settings) -> str:
    """Resume text for ranking. Priority: JOBAGENT_RESUME_TEXT (env/secret) →
    local file (dev) → empty (ranking then skipped, never a crash). No personal
    resume is ever committed to the repo."""

    if settings.resume_text.strip():
        return settings.resume_text
    path = settings.paths.resume_file
    return path.read_text(encoding="utf-8") if path.exists() else ""


def already_succeeded_today(runs: list[SchedulerRun], today: date) -> bool:
    """Idempotency guard: has a run already SUCCEEDED today? (recovers on restart)."""

    return any(
        r.status == RunStatus.SUCCESS and r.started_at is not None
        and r.started_at.astimezone(UTC).date() == today
        for r in runs
    )


async def run_daily_pipeline(container: Container, *, force: bool = False) -> SchedulerRun:
    """Execute one daily run end to end. Idempotent, audited, fails gracefully.

    Returns the ``SchedulerRun`` audit record (status SUCCESS / PARTIAL / FAILED).
    Never raises for expected operational failures — they are recorded instead.
    """

    settings = container.settings
    db = container.mongo.db
    if db is None:  # pragma: no cover - guarded by caller
        raise RuntimeError("MongoDB is not connected")

    run_id = uuid.uuid4().hex
    started = datetime.now(UTC)
    run = SchedulerRun(run_id=run_id, correlation_id=run_id, status=RunStatus.RUNNING,
                       started_at=started)
    runs_repo = RunRepository(db)

    # ---- idempotency / restart recovery -----------------------------------
    if not force and already_succeeded_today(await runs_repo.list_recent(limit=20), started.date()):
        log.info("Daily run already succeeded today — skipping (use force to override)")
        run.status = RunStatus.SUCCESS
        run.failures = ["skipped: already succeeded today"]
        return run

    await runs_repo.save(run)  # mark RUNNING so a crash is visible
    t0 = time.perf_counter()
    try:
        # ---- collector bootstrap (the API does this in create_app; the
        # standalone scheduler must do it too, or routing targets are all
        # "not registered") -------------------------------------------------
        discover_collectors()
        log.info("Collector registry ready: {} collectors", len(available_collectors()))

        # ---- sources + companies ------------------------------------------
        await container.sources.load_from(YamlSourceLoader(settings.paths.ats_sources_file))
        companies = await CompanyRepository(db).list_active()
        log.info("Loaded {} sources, {} active companies",
                 len(container.sources), len(companies))

        # ---- build work-list + collect ------------------------------------
        # require_registered_collector: skip routing targets with no registered
        # collector (e.g. the generic "career_site" fallback) instead of crashing.
        router = CompanyRouter(container.sources, RoutingConfig(require_registered_collector=True))
        work = build_work_list(companies, router)
        run.collectors_executed = [name for name, _ in work]
        log.info("Routed to {} collectors: {}", len(work), run.collectors_executed)

        ctx = CollectorContext(
            http=container.http, settings=settings,
            states=container.collector_states, benchmarks=BenchmarkRepository(db),
        )
        results = await CollectorExecutor(ctx).run_many(work)
        items: list[ProcessItem] = [
            ProcessItem(raw=raw, source=res.collector, source_type=SourceType.ATS,
                        ats_type=_ats_for(res.collector))
            for res in results for raw in res.jobs
        ]
        run.jobs_collected = len(items)
        run.failures.extend(
            f"{res.collector}: {res.errors} collector error(s)"
            for res in results if res.errors
        )
        log.info("Collected {} raw jobs across {} collectors", len(items), len(results))

        # ---- resume + priority + process (normalize→filter→dedup→embed→rank→store)
        priority = build_priority_map([c.model_dump() for c in companies])
        pipeline = get_pipeline(db, container)
        # Resume priority: JOBAGENT_RESUME_TEXT env/secret → local file (dev) →
        # none. Never commit a personal resume; production supplies it as a secret.
        resume = None
        resume_text = resolve_resume_text(settings)
        if resume_text.strip():
            resume = pipeline.build_resume_context(
                text=resume_text, max_experience_years=settings.filters.max_experience_years)
        else:
            log.warning(
                "No resume provided (set JOBAGENT_RESUME_TEXT) — "
                "jobs are collected/stored but ranking is unavailable"
            )

        result = await pipeline.process(
            items, resume=resume, company_priority=priority, persist=True,
            incremental=settings.collector.incremental, correlation_id=run_id)
        run.duplicates_removed = result.dedup.duplicates if result.dedup else 0
        run.ai_ranked = len(result.jobs)
        log.info("Pipeline: {} ranked, {} duplicates removed",
                 run.ai_ranked, run.duplicates_removed)

        # ---- report + email -----------------------------------------------
        if settings.smtp.to_address:
            record = await get_notification_service(db, container).send_report(
                report_type="daily", recipient=settings.smtp.to_address,
                attach_formats=[ReportFormat.EXCEL])
            run.excel_generated = True
            run.email_sent = record.delivery_status == DeliveryStatus.SENT
            log.info("Report emailed to configured address (sent={})", run.email_sent)
        else:
            log.warning("No SMTP to_address configured — skipping email")

        run.status = RunStatus.PARTIAL if run.failures else RunStatus.SUCCESS
    except Exception as exc:  # orchestration must fail gracefully + be recorded
        log.exception("Daily run failed: {}", exc)
        run.status = RunStatus.FAILED
        run.failures.append(f"fatal: {type(exc).__name__}: {exc}")
    finally:
        run.finished_at = datetime.now(UTC)
        run.duration_seconds = round(time.perf_counter() - t0, 3)
        await runs_repo.save(run)
        log.info("Daily run {} finished: status={} duration={}s",
                 run_id, run.status, run.duration_seconds)
    return run
