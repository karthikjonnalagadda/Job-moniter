"""Company + import/validate/sync endpoints.

* ``GET  /companies``            — list companies (paginated).
* ``GET  /companies/{slug}``     — one company by slug.
* ``POST /companies/validate``   — upload a file; validate only (no writes).
* ``POST /companies/import``     — upload a file; import (dry-run/overwrite/skip-invalid).
* ``POST /companies/sync``       — route stored companies to collectors (no crawl).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status

from app.api.deps import (
    CompanyRepositoryDep,
    get_ats_updater,
    get_company_import_service,
    get_company_router,
)
from app.importers.models import ImportOptions, ImportReport, ValidationReport
from app.importers.service import CompanyImportService
from app.models.company import Company
from app.routing.ats_updater import ATSMetadataUpdater, ATSUpdateResult
from app.routing.models import RoutingSummary
from app.routing.router import CompanyRouter

router = APIRouter(tags=["companies"])

ImportServiceDep = Annotated[CompanyImportService, Depends(get_company_import_service)]
RouterDep = Annotated[CompanyRouter, Depends(get_company_router)]
ATSUpdaterDep = Annotated[ATSMetadataUpdater, Depends(get_ats_updater)]

_ALLOWED_SUFFIXES = {".csv", ".json", ".yaml", ".yml"}


async def _spool_upload(upload: UploadFile) -> Path:
    """Persist an uploaded file to a temp path, preserving its extension."""

    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{suffix}'. Use CSV, JSON, or YAML.",
        )
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)  # noqa: SIM115
    try:
        tmp.write(await upload.read())
    finally:
        tmp.close()
    return Path(tmp.name)


@router.get("", response_model=list[Company])
async def list_companies(
    repo: CompanyRepositoryDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    skip: Annotated[int, Query(ge=0)] = 0,
    active_only: bool = False,
) -> list[Company]:
    query = {"active_status": True} if active_only else {}
    return await repo.find(query, limit=limit, skip=skip, sort=[("name", 1)])


@router.get("/{slug}", response_model=Company)
async def get_company(slug: str, repo: CompanyRepositoryDep) -> Company:
    company = await repo.get_by_slug(slug)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Company '{slug}' not found")
    return company


@router.post("/validate", response_model=ValidationReport)
async def validate_companies(file: UploadFile, service: ImportServiceDep) -> ValidationReport:
    path = await _spool_upload(file)
    try:
        return await service.validate_file(path)
    finally:
        path.unlink(missing_ok=True)


@router.post("/import", response_model=ImportReport)
async def import_companies(
    file: UploadFile,
    service: ImportServiceDep,
    dry_run: bool = False,
    overwrite: bool = True,
    skip_invalid: bool = False,
) -> ImportReport:
    path = await _spool_upload(file)
    options = ImportOptions(dry_run=dry_run, overwrite=overwrite, skip_invalid=skip_invalid)
    try:
        return await service.import_file(path, options)
    finally:
        path.unlink(missing_ok=True)


@router.post("/enrich-ats", response_model=ATSUpdateResult)
async def enrich_ats_metadata(
    repo: CompanyRepositoryDep,
    updater: ATSUpdaterDep,
    limit: Annotated[int, Query(ge=1, le=100_000)] = 10_000,
) -> ATSUpdateResult:
    """Detect and persist ATS wiring for companies whose ATS is still unknown."""

    companies = await repo.find({}, limit=limit)
    return await updater.enrich_many(companies)


@router.post("/sync", response_model=RoutingSummary)
async def sync_companies(
    repo: CompanyRepositoryDep,
    company_router: RouterDep,
    updater: ATSUpdaterDep,
    limit: Annotated[int, Query(ge=1, le=100_000)] = 10_000,
    enrich: bool = True,
) -> RoutingSummary:
    """Route stored companies to collectors and return the routing summary.

    By default this first enriches unknown-ATS companies from their career URL
    (``enrich=false`` to skip), so routing prefers a first-class ATS collector
    over the generic career crawler whenever the URL reveals the platform.
    """

    companies = await repo.find({}, limit=limit)
    if enrich:
        await updater.enrich_many(companies)
        companies = await repo.find({}, limit=limit)  # reload with new ATS wiring
    return company_router.route_all(companies)
