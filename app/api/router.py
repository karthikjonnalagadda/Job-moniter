"""Aggregate API router.

Mounts all route modules. Phase 2 wires only ``health``; the remaining endpoints
(/search, /jobs, /companies, /collectors, /preferences, /stats, /export,
/send-email) are added in their respective phases and included here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    ai,
    analytics,
    collectors,
    companies,
    exports,
    health,
    metrics,
    notifications,
    ops,
    pipeline,
    registry,
    reports,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(metrics.router)
api_router.include_router(collectors.router, prefix="/collectors")
api_router.include_router(companies.router, prefix="/companies")
api_router.include_router(registry.router, prefix="/registry")
api_router.include_router(ops.router)
api_router.include_router(pipeline.router, prefix="/pipeline")
api_router.include_router(reports.router, prefix="/reports")
api_router.include_router(analytics.router, prefix="/analytics")
api_router.include_router(exports.router, prefix="/exports")
api_router.include_router(notifications.router, prefix="/notifications")
api_router.include_router(ai.router, prefix="/ai")

# Wired in later phases:
# api_router.include_router(search.router, prefix="/search", tags=["search"])
# api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
# api_router.include_router(preferences.router, prefix="/preferences", tags=["preferences"])
