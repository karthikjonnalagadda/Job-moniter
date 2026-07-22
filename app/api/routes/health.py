"""Health & readiness endpoints.

* ``GET /health``  — liveness: process is up. Always 200 if the app responds.
* ``GET /health/ready`` — readiness: dependencies reachable (Mongo ping). Returns
  503 when a hard dependency is down so orchestrators can gate traffic.

Only these are implemented in Phase 2; the other 11 endpoints are wired in later
phases.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import Container, get_app_settings, get_container
from app.config.settings import Settings
from app.models.base import AppBaseModel

router = APIRouter(tags=["health"])


class HealthInfo(AppBaseModel):
    status: str
    app: str
    env: str
    version: str = "0.8.0"


class ReadyInfo(AppBaseModel):
    status: str
    mongo: bool
    vector_backend: str
    embedding_model: str


@router.get("/health", response_model=HealthInfo)
async def health(
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> HealthInfo:
    """Liveness probe — cheap, no external calls."""

    return HealthInfo(status="ok", app=settings.app_name, env=str(settings.env))


@router.get("/health/ready", response_model=ReadyInfo)
async def ready(
    response: Response,
    container: Annotated[Container, Depends(get_container)],
) -> ReadyInfo:
    """Readiness probe — verifies hard dependencies are reachable."""

    mongo_ok = await container.mongo.ping()
    if not mongo_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    settings = container.settings
    return ReadyInfo(
        status="ready" if mongo_ok else "degraded",
        mongo=mongo_ok,
        vector_backend=str(settings.vector.backend),
        embedding_model=settings.embedding.model_name,
    )
