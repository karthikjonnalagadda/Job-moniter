"""Metrics endpoint.

``GET /metrics`` returns a JSON snapshot by default, or Prometheus text
exposition format with ``?format=prometheus`` — so a Prometheus scraper /
Grafana can be pointed at it later with no code change.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from app.api.deps import Container, get_container
from app.metrics.base import MetricsSnapshot

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_model=None)
async def metrics(
    container: Annotated[Container, Depends(get_container)],
    output_format: Annotated[Literal["json", "prometheus"], Query(alias="format")] = "json",
) -> MetricsSnapshot | PlainTextResponse:
    """Expose application metrics as JSON (default) or Prometheus text."""

    sink = container.metrics
    if output_format == "prometheus":
        return PlainTextResponse(
            sink.render_prometheus(), media_type="text/plain; version=0.0.4"
        )
    return sink.snapshot()
