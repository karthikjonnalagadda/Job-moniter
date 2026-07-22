"""Company import orchestration.

Pipeline: parse → validate (per-row + cross-row) → apply (batched upsert). Honours
dry-run (write nothing), skip-invalid (import valid rows only), overwrite
(update vs skip existing), and rollback-on-failure (compensating delete of this
run's inserts). Returns an ``ImportReport`` with full statistics.

Note on rollback: MongoDB multi-document transactions require a replica set
(Atlas provides one). This service uses a portable compensating-delete rollback
(undo the inserts this run made) so it also works on standalone/local Mongo. On
Atlas a future enhancement can wrap the apply phase in a session transaction.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.config.logging import get_logger
from app.importers.models import ImportOptions, ImportReport, ImportStats, ValidationReport
from app.importers.parsers import parse_records
from app.importers.records import ImportRecord
from app.importers.validation import CompanyValidator
from app.models.common import DEFAULT_USER_ID
from app.models.company import Company

if TYPE_CHECKING:
    from app.db.repositories.companies import CompanyRepository
    from app.db.repositories.dead_letters import DeadLetterRepository
    from app.db.repositories.import_history import ImportHistoryRepository
    from app.importers.aliases import AliasResolver

log = get_logger("import")

ValidRow = tuple[int, Company]


def _chunks(items: list[ValidRow], size: int) -> list[list[ValidRow]]:
    return [items[i : i + size] for i in range(0, len(items), size)] or [[]]


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


class CompanyImportService:
    """Validates and imports company records from a file.

    Optional collaborators enable Phase-4.1 features without changing callers
    that don't use them: ``dead_letters`` (route invalid rows to a DLQ),
    ``history`` (persist a versioned import record), and ``aliases`` (fold alias
    companies onto their canonical identity).
    """

    def __init__(
        self,
        repo: CompanyRepository,
        *,
        validator: CompanyValidator | None = None,
        dead_letters: DeadLetterRepository | None = None,
        history: ImportHistoryRepository | None = None,
        aliases: AliasResolver | None = None,
    ) -> None:
        self._repo = repo
        self._validator = validator or CompanyValidator()
        self._dead_letters = dead_letters
        self._history = history
        self._aliases = aliases

    async def validate_file(self, path: Path) -> ValidationReport:
        """Parse and validate a file without writing anything."""

        records = list(parse_records(path))
        _, report = self._validator.validate(records)
        log.info(
            "Validated {} ({} valid, {} invalid, {} issues)",
            path.name,
            report.valid_rows,
            report.invalid_rows,
            len(report.issues),
        )
        return report

    async def import_file(
        self,
        path: Path,
        options: ImportOptions | None = None,
        *,
        user_id: str = DEFAULT_USER_ID,
    ) -> ImportReport:
        """Run the full import pipeline for ``path``."""

        options = options or ImportOptions()
        import_id = uuid.uuid4().hex
        checksum = _checksum(path)
        started_wall = datetime.now(tz=UTC)
        started = time.perf_counter()

        records = list(parse_records(path))
        valid, report = self._validator.validate(records)

        # Fold alias companies onto their canonical identity for dedup.
        if self._aliases is not None:
            valid = [(row, self._aliases.apply(company)) for row, company in valid]

        duplicates = sum(1 for i in report.issues if i.code.startswith("duplicate_"))
        stats = ImportStats(
            total=report.total_rows,
            valid=report.valid_rows,
            invalid=report.invalid_rows,
            duplicates=duplicates,
        )

        # Route invalid rows to the dead-letter queue (if configured).
        await self._record_dead_letters(path, records, report, import_id)

        rolled_back = False
        if not report.is_valid and not options.skip_invalid:
            log.warning("Import aborted: {} errors and skip_invalid=False", len(report.errors))
        elif options.dry_run:
            log.info("Dry-run: would import {} companies from {}", len(valid), path.name)
        else:
            rolled_back = await self._apply(valid, options, stats)

        result = self._finish(
            path,
            options,
            stats,
            report,
            started,
            import_id=import_id,
            checksum=checksum,
            rolled_back=rolled_back,
        )
        await self._persist_history(result, user_id, started_wall)
        return result

    # ---- apply phase ----------------------------------------------------
    async def _apply(
        self, valid: list[ValidRow], options: ImportOptions, stats: ImportStats
    ) -> bool:
        inserted_slugs: list[str] = []
        try:
            for batch in _chunks(valid, options.batch_size):
                for _row, company in batch:
                    existing = await self._repo.get_by_slug(company.slug)
                    if existing is not None and not options.overwrite:
                        stats.skipped += 1
                        continue
                    await self._repo.upsert_by_slug(company)
                    if existing is not None:
                        stats.updated += 1
                    else:
                        stats.inserted += 1
                        inserted_slugs.append(company.slug)
            log.info(
                "Import applied: {} inserted, {} updated, {} skipped",
                stats.inserted,
                stats.updated,
                stats.skipped,
            )
            return False
        except Exception as exc:  # apply failure -> optional rollback
            stats.failed += 1
            log.error("Import apply failed: {}", exc)
            if options.rollback_on_failure and inserted_slugs:
                for slug in inserted_slugs:
                    await self._repo.delete_by_slug(slug)
                stats.inserted = 0
                log.warning("Rolled back {} inserted companies", len(inserted_slugs))
                return True
            return False

    def _finish(
        self,
        path: Path,
        options: ImportOptions,
        stats: ImportStats,
        report: ValidationReport,
        started: float,
        *,
        import_id: str,
        checksum: str,
        rolled_back: bool,
    ) -> ImportReport:
        return ImportReport(
            import_id=import_id,
            source_file=path.name,
            checksum=checksum,
            dry_run=options.dry_run,
            rolled_back=rolled_back,
            duration_seconds=round(time.perf_counter() - started, 4),
            stats=stats,
            validation=report,
        )

    # ---- Phase 4.1 side-channels ---------------------------------------
    async def _record_dead_letters(
        self,
        path: Path,
        records: list[tuple[int, dict[str, object]]],
        report: ValidationReport,
        import_id: str,
    ) -> None:
        if self._dead_letters is None:
            return
        raw_by_row = {row: raw for row, raw in records}
        reasons: dict[int, list[str]] = {}
        for issue in report.errors:
            if issue.row is not None:
                reasons.setdefault(issue.row, []).append(f"{issue.code}: {issue.message}")
        for row, messages in reasons.items():
            await self._dead_letters.record(
                kind="import_row",
                source=path.name,
                reason="; ".join(messages),
                payload=dict(raw_by_row.get(row, {})),
                import_id=import_id,
            )
        if reasons:
            log.info("Recorded {} dead-letter rows for import {}", len(reasons), import_id)

    async def _persist_history(
        self, report: ImportReport, user_id: str, started_wall: datetime
    ) -> None:
        if self._history is None or report.import_id is None:
            return
        await self._history.save(
            ImportRecord(
                import_id=report.import_id,
                filename=report.source_file,
                checksum=report.checksum,
                user_id=user_id,
                started_at=started_wall,
                duration_seconds=report.duration_seconds,
                dry_run=report.dry_run,
                rolled_back=report.rolled_back,
                stats=report.stats,
            )
        )
