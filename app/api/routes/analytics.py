"""Analytics endpoints — aggregate views over stored jobs, runs, and collectors."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import AnalyticsServiceDep
from app.models.analytics import (
    AnalyticsReport,
    CountStat,
    MatchTrend,
    PipelinePerf,
    SalaryStat,
    TrendPoint,
)

router = APIRouter(tags=["analytics"])


class SkillsAnalytics(BaseModel):
    skills: list[CountStat]
    technologies: list[CountStat]


class TrendsAnalytics(BaseModel):
    hiring_trends: list[TrendPoint]
    match_trends: list[MatchTrend]
    pipeline_performance: PipelinePerf | None = None


@router.get("", response_model=AnalyticsReport)
async def analytics(service: AnalyticsServiceDep) -> AnalyticsReport:
    """Full analytics surface (counts, salaries, trends, pipeline performance)."""

    return await service.build()


@router.get("/skills", response_model=SkillsAnalytics)
async def skills(service: AnalyticsServiceDep) -> SkillsAnalytics:
    report = await service.build()
    return SkillsAnalytics(skills=report.skills, technologies=report.technologies)


@router.get("/companies", response_model=list[CountStat])
async def companies(service: AnalyticsServiceDep) -> list[CountStat]:
    return (await service.build()).companies


@router.get("/locations", response_model=list[CountStat])
async def locations(service: AnalyticsServiceDep) -> list[CountStat]:
    return (await service.build()).locations


@router.get("/salaries", response_model=list[SalaryStat])
async def salaries(service: AnalyticsServiceDep) -> list[SalaryStat]:
    return (await service.build()).salaries


@router.get("/trends", response_model=TrendsAnalytics)
async def trends(service: AnalyticsServiceDep) -> TrendsAnalytics:
    report = await service.build()
    return TrendsAnalytics(
        hiring_trends=report.hiring_trends,
        match_trends=report.match_trends,
        pipeline_performance=report.pipeline_performance,
    )
