"""Collector introspection endpoints.

Exposes the registered collector plugins and their capability metadata so
operators and the future dashboard can see, at runtime, which sources exist,
what they support, and their legal mode — without reading code.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import BenchmarkRepositoryDep, get_collector_states
from app.collectors import CollectorMetadata, describe_all, get_collector_class
from app.collectors.base import CollectorHealthReport
from app.collectors.state import CollectorStateInfo, CollectorStateRegistry
from app.core.exceptions import ConfigurationError
from app.models.collector_benchmark import CollectorBenchmark

router = APIRouter(tags=["collectors"])

StatesDep = Annotated[CollectorStateRegistry, Depends(get_collector_states)]


@router.get("", response_model=list[CollectorMetadata])
async def list_collectors() -> list[CollectorMetadata]:
    """Return capability metadata for every registered collector (priority-sorted)."""

    return describe_all()


@router.get("/{name}", response_model=CollectorMetadata)
async def get_collector(name: str) -> CollectorMetadata:
    """Return capability metadata for one collector by registry name."""

    try:
        return get_collector_class(name).describe()
    except ConfigurationError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=exc.message) from exc


@router.get("/{name}/health", response_model=CollectorHealthReport)
async def collector_health(name: str) -> CollectorHealthReport:
    """Run a collector's startup/config/dependency/connectivity probes."""

    try:
        collector = get_collector_class(name)()
    except ConfigurationError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=exc.message) from exc
    return await collector.health_check()


@router.get("/{name}/stats", response_model=CollectorBenchmark)
async def collector_stats(name: str, repo: BenchmarkRepositoryDep) -> CollectorBenchmark:
    """Return rolling benchmark stats (response time, success/error/dup rates)."""

    benchmark = await repo.get_for(name)
    if benchmark is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"No benchmark for '{name}'")
    return benchmark


@router.get("/{name}/state", response_model=CollectorStateInfo)
async def collector_state(name: str, states: StatesDep) -> CollectorStateInfo:
    """Return the collector's current lifecycle state (idle/syncing/failed/...)."""

    try:
        get_collector_class(name)  # 404 if unknown
    except ConfigurationError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=exc.message) from exc
    return states.get(name).info()
