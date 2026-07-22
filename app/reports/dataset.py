"""Report dataset — the single assembled view every exporter/report consumes.

Built once from the repositories + analytics service, then handed to the Excel /
CSV / JSON / HTML / PDF exporters so no format recomputes anything. Also carries
the version stamps (report/schema/pipeline/collector) required on every report.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import Field

from app.core.dedup.hashing import content_fingerprint
from app.models.analytics import AnalyticsReport, CountStat
from app.models.base import AppBaseModel
from app.models.collector_benchmark import CollectorBenchmark
from app.models.common import DEFAULT_USER_ID
from app.models.job import Job
from app.models.pipeline_run import PipelineRun
from app.reports.versioning import ReportVersions, build_versions

if TYPE_CHECKING:
    from app.analytics.service import AnalyticsService
    from app.db.repositories.benchmarks import BenchmarkRepository
    from app.db.repositories.jobs import JobRepository
    from app.db.repositories.pipeline_runs import PipelineRunRepository


class DuplicateGroup(AppBaseModel):
    """A set of stored jobs sharing a content fingerprint (near-duplicates)."""

    fingerprint: str
    count: int
    labels: list[str] = Field(default_factory=list)  # "Company — Role"


class ReportData(AppBaseModel):
    """Everything a report needs, assembled once."""

    title: str = "AI Job Intelligence Report"
    generated_at: datetime | None = None
    run_id: str | None = None
    versions: ReportVersions = Field(default_factory=ReportVersions)

    analytics: AnalyticsReport = Field(default_factory=AnalyticsReport)
    jobs: list[Job] = Field(default_factory=list)
    top_matches: list[Job] = Field(default_factory=list)
    duplicate_groups: list[DuplicateGroup] = Field(default_factory=list)
    skill_gap: list[CountStat] = Field(default_factory=list)  # most-common missing skills
    collector_stats: list[CollectorBenchmark] = Field(default_factory=list)
    pipeline_runs: list[PipelineRun] = Field(default_factory=list)

    @property
    def new_today(self) -> int:
        if self.generated_at is None:
            return 0
        today = self.generated_at.date()
        return sum(1 for j in self.jobs if j.posted_date and j.posted_date.date() == today)


class ReportDatasetBuilder:
    """Assembles a ``ReportData`` from the repositories + analytics service."""

    def __init__(
        self,
        jobs: JobRepository,
        analytics: AnalyticsService,
        *,
        runs: PipelineRunRepository | None = None,
        benchmarks: BenchmarkRepository | None = None,
    ) -> None:
        self._jobs = jobs
        self._analytics = analytics
        self._runs = runs
        self._benchmarks = benchmarks

    async def build(
        self,
        *,
        user_id: str = DEFAULT_USER_ID,
        top_n_matches: int = 50,
        now: datetime | None = None,
        collector_versions: dict[str, str] | None = None,
    ) -> ReportData:
        jobs = await self._jobs.find({"user_id": user_id}, limit=100_000)
        jobs.sort(key=lambda j: j.match.score if j.match else 0.0, reverse=True)
        analytics = await self._analytics.build(user_id=user_id)

        pipeline_runs = await self._runs.list_recent(limit=50) if self._runs else []
        collector_stats = await self._benchmarks.list_all() if self._benchmarks else []

        return ReportData(
            generated_at=now or datetime.now(tz=UTC),
            run_id=pipeline_runs[0].run_id if pipeline_runs else None,
            versions=build_versions(collector_versions or self._collector_versions()),
            analytics=analytics,
            jobs=jobs,
            top_matches=jobs[:top_n_matches],
            duplicate_groups=self._duplicate_groups(jobs),
            skill_gap=self._skill_gap(jobs),
            collector_stats=collector_stats,
            pipeline_runs=pipeline_runs,
        )

    @staticmethod
    def _collector_versions() -> dict[str, str]:
        from app.collectors.registry import describe_all

        return {m.name: m.version for m in describe_all() if m.supported_ats}

    @staticmethod
    def _duplicate_groups(jobs: list[Job]) -> list[DuplicateGroup]:
        by_fp: dict[str, list[Job]] = defaultdict(list)
        for job in jobs:
            fp = job.content_fingerprint or content_fingerprint(job.role, job.description)
            if fp:
                by_fp[fp].append(job)
        groups = [
            DuplicateGroup(
                fingerprint=fp,
                count=len(group),
                labels=[f"{j.company_name} — {j.normalized_role or j.role}" for j in group],
            )
            for fp, group in by_fp.items()
            if len(group) > 1
        ]
        return sorted(groups, key=lambda g: -g.count)

    @staticmethod
    def _skill_gap(jobs: list[Job], *, top_n: int = 20) -> list[CountStat]:
        missing: Counter[str] = Counter()
        for job in jobs:
            if job.match is not None:
                missing.update(job.match.missing_skills)
        return [CountStat(label=s, count=c) for s, c in missing.most_common(top_n)]
