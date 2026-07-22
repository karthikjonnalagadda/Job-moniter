"""Company import service against in-memory Mongo (all formats + options)."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.db.repositories.companies import CompanyRepository
from app.importers.models import ImportOptions
from app.importers.service import CompanyImportService

_CSV = (
    "company,slug,ats,ats_token,career_url,country\n"
    "Acme,acme,greenhouse,acme,https://acme.example/careers,US\n"
    "Globex,globex,lever,globex,https://globex.example/jobs,US\n"
)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


async def test_import_csv_inserts_and_upserts(mock_db, tmp_path: Path) -> None:
    repo = CompanyRepository(mock_db)
    service = CompanyImportService(repo)
    path = _write(tmp_path, "c.csv", _CSV)

    report = await service.import_file(path, ImportOptions())
    assert report.stats.total == 2
    assert report.stats.inserted == 2
    assert await repo.count() == 2

    # re-import updates (no duplicates)
    report2 = await service.import_file(path, ImportOptions())
    assert report2.stats.updated == 2
    assert await repo.count() == 2


async def test_dry_run_writes_nothing(mock_db, tmp_path: Path) -> None:
    repo = CompanyRepository(mock_db)
    report = await CompanyImportService(repo).import_file(
        _write(tmp_path, "c.csv", _CSV), ImportOptions(dry_run=True)
    )
    assert report.dry_run is True
    assert report.stats.valid == 2
    assert await repo.count() == 0


async def test_import_json_and_yaml(mock_db, tmp_path: Path) -> None:
    repo = CompanyRepository(mock_db)
    service = CompanyImportService(repo)

    json_doc = '{"companies":[{"company":"Acme","slug":"acme","ats":"greenhouse","ats_token":"a"}]}'
    r1 = await service.import_file(_write(tmp_path, "c.json", json_doc), ImportOptions())
    assert r1.stats.inserted == 1

    yaml_doc = "companies:\n  - company: Globex\n    slug: globex\n    ats: lever\n"
    r2 = await service.import_file(_write(tmp_path, "c.yaml", yaml_doc), ImportOptions())
    assert r2.stats.inserted == 1
    assert await repo.count() == 2


async def test_invalid_rows_abort_unless_skip_invalid(mock_db, tmp_path: Path) -> None:
    repo = CompanyRepository(mock_db)
    service = CompanyImportService(repo)
    bad = "company,slug,ats\nAcme,acme,greenhouse\nNoSlug,,lever\n"  # row 2 missing slug
    path = _write(tmp_path, "bad.csv", bad)

    aborted = await service.import_file(path, ImportOptions())
    assert aborted.stats.inserted == 0  # aborted, nothing written
    assert await repo.count() == 0

    skipped = await service.import_file(path, ImportOptions(skip_invalid=True))
    assert skipped.stats.inserted == 1  # valid row imported
    assert skipped.stats.invalid == 1


async def test_no_overwrite_skips_existing(mock_db, tmp_path: Path) -> None:
    repo = CompanyRepository(mock_db)
    service = CompanyImportService(repo)
    path = _write(tmp_path, "c.csv", _CSV)
    await service.import_file(path, ImportOptions())

    report = await service.import_file(path, ImportOptions(overwrite=False))
    assert report.stats.skipped == 2
    assert report.stats.updated == 0


async def test_rollback_on_apply_failure(
    mock_db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = CompanyRepository(mock_db)
    service = CompanyImportService(repo)
    path = _write(tmp_path, "c.csv", _CSV)

    calls = {"n": 0}
    real_upsert = repo.upsert_by_slug

    async def flaky_upsert(company):  # fail on the 2nd upsert
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return await real_upsert(company)

    monkeypatch.setattr(repo, "upsert_by_slug", flaky_upsert)
    report = await service.import_file(path, ImportOptions(rollback_on_failure=True))
    assert report.rolled_back is True
    assert report.stats.inserted == 0
    assert await repo.count() == 0  # first insert was compensated
