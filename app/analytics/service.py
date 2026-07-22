"""Analytics service — computes aggregate statistics over stored data.

Loads stored jobs once and derives every count/trend in Python (portable,
testable with mongomock, fine for 10k+ records). Collector stats come from the
benchmark repository; pipeline performance from the run repository.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import TYPE_CHECKING

from app.config.logging import get_logger
from app.models.analytics import (
    AnalyticsReport,
    CountStat,
    MatchTrend,
    PipelinePerf,
    SalaryStat,
    TrendPoint,
)
from app.models.common import DEFAULT_USER_ID

if TYPE_CHECKING:
    from app.db.repositories.benchmarks import BenchmarkRepository
    from app.db.repositories.jobs import JobRepository
    from app.db.repositories.pipeline_runs import PipelineRunRepository
    from app.models.collector_benchmark import CollectorBenchmark
    from app.models.job import Job

log = get_logger("api")

_SCORE_BUCKETS = ((90, "90-100"), (75, "75-89"), (50, "50-74"), (0, "0-49"))


def _top(counter: Counter[str], limit: int) -> list[CountStat]:
    return [CountStat(label=label, count=count) for label, count in counter.most_common(limit)]


def _score_bucket(score: float) -> str:
    for threshold, label in _SCORE_BUCKETS:
        if score >= threshold:
            return label
    return "0-49"


class AnalyticsService:
    """Aggregates jobs/runs/benchmarks into an ``AnalyticsReport``."""

    def __init__(
        self,
        jobs: JobRepository,
        *,
        runs: PipelineRunRepository | None = None,
        benchmarks: BenchmarkRepository | None = None,
    ) -> None:
        self._jobs = jobs
        self._runs = runs
        self._benchmarks = benchmarks

    async def build(
        self, *, user_id: str = DEFAULT_USER_ID, top_n: int = 10, job_limit: int = 100_000
    ) -> AnalyticsReport:
        jobs = await self._jobs.find({"user_id": user_id}, limit=job_limit)
        report = self._from_jobs(jobs, top_n=top_n)
        if self._runs is not None:
            report.pipeline_performance = await self.pipeline_performance()
        return report

    def _from_jobs(self, jobs: list[Job], *, top_n: int) -> AnalyticsReport:
        companies: Counter[str] = Counter()
        roles: Counter[str] = Counter()
        technologies: Counter[str] = Counter()
        skills: Counter[str] = Counter()
        locations: Counter[str] = Counter()
        employment: Counter[str] = Counter()
        scores: list[float] = []

        for job in jobs:
            companies[job.canonical_company_name or job.company_name] += 1
            roles[job.normalized_role or job.role] += 1
            technologies.update(job.technologies)
            skills.update(job.skills)
            loc = job.location.city or job.location.country or (
                "Remote" if job.location.is_remote else "Unknown"
            )
            locations[loc] += 1
            employment[str(job.employment_type)] += 1
            if job.match is not None:
                scores.append(job.match.score)

        return AnalyticsReport(
            total_jobs=len(jobs),
            ranked_jobs=len(scores),
            average_match=round(statistics.mean(scores), 2) if scores else 0.0,
            companies=_top(companies, top_n),
            roles=_top(roles, top_n),
            technologies=_top(technologies, top_n),
            skills=_top(skills, top_n),
            locations=_top(locations, top_n),
            employment_types=_top(employment, top_n),
            salaries=self._salary_stats(jobs),
            hiring_trends=self._hiring_trends(jobs),
            match_trends=self._match_trends(jobs),
        )

    def _salary_stats(self, jobs: list[Job]) -> list[SalaryStat]:
        by_bucket: dict[tuple[str, str], list[float]] = defaultdict(list)
        for job in jobs:
            s = job.salary
            if s is None or s.min_amount is None:
                continue
            amount = (s.min_amount + (s.max_amount or s.min_amount)) / 2
            by_bucket[(s.currency or "?", s.period or "year")].append(amount)
        out: list[SalaryStat] = []
        for (currency, period), amounts in by_bucket.items():
            out.append(
                SalaryStat(
                    currency=currency,
                    period=period,
                    count=len(amounts),
                    min_amount=round(min(amounts), 2),
                    max_amount=round(max(amounts), 2),
                    avg_amount=round(statistics.mean(amounts), 2),
                    median_amount=round(statistics.median(amounts), 2),
                )
            )
        return sorted(out, key=lambda s: -s.count)

    def _hiring_trends(self, jobs: list[Job]) -> list[TrendPoint]:
        by_day: Counter[str] = Counter()
        for job in jobs:
            if job.posted_date is not None:
                by_day[job.posted_date.date().isoformat()] += 1
        return [TrendPoint(bucket=day, count=count) for day, count in sorted(by_day.items())]

    def _match_trends(self, jobs: list[Job]) -> list[MatchTrend]:
        by_resume: dict[str | None, list[float]] = defaultdict(list)
        for job in jobs:
            if job.match is not None:
                by_resume[job.match.resume_id].append(job.match.score)
        trends: list[MatchTrend] = []
        for resume_id, scores in by_resume.items():
            buckets: Counter[str] = Counter(_score_bucket(s) for s in scores)
            trends.append(
                MatchTrend(
                    resume_id=resume_id,
                    ranked_jobs=len(scores),
                    avg_score=round(statistics.mean(scores), 2),
                    max_score=round(max(scores), 2),
                    buckets=dict(buckets),
                )
            )
        return sorted(trends, key=lambda t: -t.ranked_jobs)

    # ---- collector + pipeline ------------------------------------------
    async def collector_stats(self) -> list[CollectorBenchmark]:
        if self._benchmarks is None:
            return []
        return await self._benchmarks.list_all()

    async def pipeline_performance(self, *, limit: int = 100) -> PipelinePerf:
        if self._runs is None:
            return PipelinePerf(
                total_runs=0, total_collected=0, total_stored=0,
                total_duplicates=0, total_filtered_out=0, avg_duration_seconds=0.0,
            )
        runs = await self._runs.list_recent(limit=limit)
        if not runs:
            return PipelinePerf(
                total_runs=0, total_collected=0, total_stored=0,
                total_duplicates=0, total_filtered_out=0, avg_duration_seconds=0.0,
            )
        stage_totals: dict[str, list[float]] = defaultdict(list)
        for run in runs:
            for stage in run.stages:
                stage_totals[stage.name].append(stage.duration_ms)
        return PipelinePerf(
            total_runs=len(runs),
            total_collected=sum(r.collected for r in runs),
            total_stored=sum(r.stored for r in runs),
            total_duplicates=sum(r.duplicates for r in runs),
            total_filtered_out=sum(r.filtered_out for r in runs),
            avg_duration_seconds=round(statistics.mean(r.duration_seconds for r in runs), 4),
            avg_stage_ms={
                name: round(statistics.mean(vals), 3) for name, vals in stage_totals.items()
            },
        )
