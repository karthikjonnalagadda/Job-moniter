"""Continuous ATS-metadata enrichment of stored companies."""

from __future__ import annotations

from app.db.repositories.companies import CompanyRepository
from app.models.company import Company
from app.models.enums import ATSType
from app.routing.ats_updater import ATSMetadataUpdater


async def test_enrich_fills_unknown_ats(mock_db) -> None:
    repo = CompanyRepository(mock_db)
    await repo.upsert_by_slug(
        Company(name="DemoCo", slug="democo", career_url="https://jobs.lever.co/democo")
    )
    updater = ATSMetadataUpdater(repo)

    company = await repo.get_by_slug("democo")
    assert company is not None
    updated = await updater.enrich(company)

    assert updated is not None
    assert updated.ats_type == ATSType.LEVER
    assert updated.ats_token == "democo"
    assert updated.career_platform == "Lever"


async def test_enrich_skips_known_ats(mock_db) -> None:
    repo = CompanyRepository(mock_db)
    await repo.upsert_by_slug(
        Company(
            name="SetCo",
            slug="setco",
            ats_type=ATSType.GREENHOUSE,
            career_url="https://jobs.lever.co/setco",
        )
    )
    updater = ATSMetadataUpdater(repo)
    company = await repo.get_by_slug("setco")
    assert company is not None
    # already has an ATS -> never overwritten
    assert await updater.enrich(company) is None


async def test_enrich_many_reports_counts(mock_db) -> None:
    repo = CompanyRepository(mock_db)
    await repo.upsert_by_slug(
        Company(name="A", slug="a", career_url="https://a.recruitee.com")
    )
    await repo.upsert_by_slug(
        Company(name="B", slug="b", career_url="https://www.example.com/careers")
    )
    updater = ATSMetadataUpdater(repo)
    result = await updater.enrich_many(await repo.list_active())
    assert result.scanned == 2
    assert result.updated == 1  # only the Recruitee one is detectable
    assert result.updated_slugs == ["a"]
