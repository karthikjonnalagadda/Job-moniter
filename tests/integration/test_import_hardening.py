"""Import versioning, dead-letter queue, and alias folding (Phase 4.1)."""

from __future__ import annotations

from pathlib import Path

from app.db.repositories.companies import CompanyRepository
from app.db.repositories.dead_letters import DeadLetterRepository
from app.db.repositories.import_history import ImportHistoryRepository
from app.importers.aliases import AliasResolver
from app.importers.models import ImportOptions
from app.importers.service import CompanyImportService

_CSV_WITH_BAD = "company,slug,ats\nAcme,acme,greenhouse\nBad,,lever\n"  # row 2 missing slug


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "c.csv"
    path.write_text(content, encoding="utf-8")
    return path


async def test_import_id_checksum_and_history(mock_db, tmp_path: Path) -> None:
    history = ImportHistoryRepository(mock_db)
    service = CompanyImportService(CompanyRepository(mock_db), history=history)
    path = _write(tmp_path, "company,slug,ats,ats_token\nAcme,acme,greenhouse,a\n")

    report = await service.import_file(path, ImportOptions(), user_id="default")
    assert report.import_id is not None
    assert report.checksum is not None and len(report.checksum) == 64

    record = await history.get_by_import_id(report.import_id)
    assert record is not None
    assert record.stats.inserted == 1
    assert record.filename == "c.csv"
    assert record.rolled_back is False


async def test_invalid_rows_go_to_dead_letter_queue(mock_db, tmp_path: Path) -> None:
    dlq = DeadLetterRepository(mock_db)
    service = CompanyImportService(CompanyRepository(mock_db), dead_letters=dlq)
    report = await service.import_file(
        _write(tmp_path, _CSV_WITH_BAD), ImportOptions(skip_invalid=True)
    )

    entries = await dlq.list_unreplayed()
    assert len(entries) == 1
    dl = entries[0]
    assert dl.kind == "import_row"
    assert dl.import_id == report.import_id
    assert "missing_required_field" in dl.reason


async def test_alias_folding_sets_canonical(mock_db, tmp_path: Path) -> None:
    aliases = AliasResolver.from_file(Path("data/company_aliases.yaml"))
    repo = CompanyRepository(mock_db)
    service = CompanyImportService(repo, aliases=aliases)
    await service.import_file(_write(tmp_path, "company,slug\nGoogle,google\n"), ImportOptions())

    stored = await repo.get_by_slug("google")
    assert stored is not None
    assert stored.canonical_slug == "alphabet"
    assert "Google" in stored.aliases
