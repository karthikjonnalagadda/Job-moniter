"""End-to-end: build the Indian dataset and import it into (mock) MongoDB.

Proves the fourth output target — MongoDB — using the same generated artifacts
and the existing ``CompanyImportService`` (one validation/upsert path).
"""

from __future__ import annotations

from pathlib import Path

from app.db.repositories.companies import CompanyRepository
from app.importers.india_seed import IndiaSeedBuilder
from app.importers.service import CompanyImportService
from app.models.enums import ATSType

_SEED = Path("data/companies/Indian_Company_Career_Sites.csv")
_METADATA = Path("data/companies/indian_company_metadata.yaml")


async def test_build_and_import_into_mongo(mock_db, tmp_path) -> None:
    builder = IndiaSeedBuilder()
    records = builder.build(_SEED, _METADATA)
    assert len(records) >= 200  # scaled well beyond the seed's ~74

    paths = builder.write_outputs(records, tmp_path)
    service = CompanyImportService(CompanyRepository(mock_db))
    report = await service.import_file(paths["yaml"])

    assert report.validation.invalid_rows == 0
    assert report.stats.inserted == len(records)

    repo = CompanyRepository(mock_db)
    assert await repo.count() == len(records)

    # A known Lever-hosted company keeps its ATS wiring through the round-trip.
    lever_companies = await repo.list_by_ats(ATSType.LEVER)
    assert lever_companies, "expected at least one Lever-routed company"
    sample = lever_companies[0]
    assert sample.ats_type == ATSType.LEVER
    assert sample.company_category is not None


async def test_import_is_idempotent(mock_db, tmp_path) -> None:
    builder = IndiaSeedBuilder()
    records = builder.build(_SEED, _METADATA)
    paths = builder.write_outputs(records, tmp_path)
    service = CompanyImportService(CompanyRepository(mock_db))

    first = await service.import_file(paths["yaml"])
    second = await service.import_file(paths["yaml"])  # re-import same file

    assert first.stats.inserted == len(records)
    assert second.stats.inserted == 0  # all upserts, no new docs
    assert second.stats.updated == len(records)
    assert await CompanyRepository(mock_db).count() == len(records)
