"""Phase-4/5 operator CLIs.

Entry points (registered in pyproject ``[project.scripts]``):
    job-agent-import <file>          import companies (CSV/JSON/YAML)
    job-agent-validate <file>        validate a company file (no writes)
    job-agent-sync                   route stored companies to collectors
    job-agent-list-collectors        list discovered collector plugins
    job-agent-build-india            build the Indian company dataset (CSV/JSON/YAML[/Mongo])

Shared flags where applicable: --verbose, --dry-run, --overwrite/--no-overwrite,
--skip-invalid.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.api.deps import Container, build_container
from app.collectors.loader import discover_collectors
from app.collectors.registry import describe_all
from app.config.logging import configure_logging, get_logger
from app.config.settings import Settings, get_settings
from app.db.repositories.companies import CompanyRepository
from app.importers.india_seed import IndiaSeedBuilder
from app.importers.models import ImportOptions
from app.importers.service import CompanyImportService
from app.registry.loaders import YamlSourceLoader
from app.registry.service import SourceRegistry
from app.routing.ats_updater import ATSMetadataUpdater
from app.routing.router import CompanyRouter

log = get_logger("import")


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _bootstrap(verbose: bool) -> tuple[Settings, Container]:
    settings = get_settings()
    if verbose:
        settings.log_level = "DEBUG"
    configure_logging(settings)
    return settings, build_container(settings)


# ---------------------------------------------------------------------------
# job-agent-import
# ---------------------------------------------------------------------------
async def _import(path: Path, options: ImportOptions, verbose: bool) -> int:
    _, container = _bootstrap(verbose)
    await container.mongo.connect()
    try:
        service = CompanyImportService(CompanyRepository(container.mongo.db))
        report = await service.import_file(path, options)
        _print(report.model_dump())
        ok = report.validation.is_valid or options.skip_invalid
        return 0 if ok and not report.rolled_back and report.stats.failed == 0 else 1
    finally:
        await container.mongo.disconnect()


def import_main() -> None:
    parser = argparse.ArgumentParser(description="Import companies from CSV/JSON/YAML.")
    parser.add_argument("file", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true", default=True)
    parser.add_argument("--no-overwrite", dest="overwrite", action="store_false")
    parser.add_argument("--skip-invalid", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    options = ImportOptions(
        dry_run=args.dry_run, overwrite=args.overwrite, skip_invalid=args.skip_invalid
    )
    raise SystemExit(asyncio.run(_import(args.file, options, args.verbose)))


# ---------------------------------------------------------------------------
# job-agent-validate
# ---------------------------------------------------------------------------
async def _validate(path: Path, verbose: bool) -> int:
    _, container = _bootstrap(verbose)
    # Validation needs no DB; build a repo against a (possibly unconnected) handle.
    await container.mongo.connect()
    try:
        service = CompanyImportService(CompanyRepository(container.mongo.db))
        report = await service.validate_file(path)
        _print(report.model_dump())
        return 0 if report.is_valid else 1
    finally:
        await container.mongo.disconnect()


def validate_main() -> None:
    parser = argparse.ArgumentParser(description="Validate a company file (no writes).")
    parser.add_argument("file", type=Path)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_validate(args.file, args.verbose)))


# ---------------------------------------------------------------------------
# job-agent-sync
# ---------------------------------------------------------------------------
async def _sync(verbose: bool) -> int:
    settings, container = _bootstrap(verbose)
    await container.mongo.connect()
    try:
        if not await container.mongo.ping():
            log.error("MongoDB not reachable — cannot sync")
            return 1
        registry = SourceRegistry()
        if settings.paths.ats_sources_file.exists():
            await registry.load_from(YamlSourceLoader(settings.paths.ats_sources_file))
        repo = CompanyRepository(container.mongo.db)
        companies = await repo.find({}, limit=100_000)
        # Continuously enrich ATS metadata before routing (career-site rule #5).
        enrichment = await ATSMetadataUpdater(repo).enrich_many(companies)
        if enrichment.updated:
            companies = await repo.find({}, limit=100_000)  # reload with new wiring
        summary = CompanyRouter(registry).route_all(companies)
        _print(
            {
                "ats_enrichment": enrichment.model_dump(exclude={"updated_slugs"}),
                **summary.model_dump(exclude={"decisions"}),
            }
        )
        return 0
    finally:
        await container.mongo.disconnect()


def sync_main() -> None:
    parser = argparse.ArgumentParser(description="Route stored companies to collectors.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_sync(args.verbose)))


# ---------------------------------------------------------------------------
# job-agent-build-india
# ---------------------------------------------------------------------------
async def _build_india(out_dir: Path, do_import: bool, dry_run: bool, verbose: bool) -> int:
    settings, container = _bootstrap(verbose)
    builder = IndiaSeedBuilder()
    records = builder.build(settings.paths.indian_seed_file, settings.paths.indian_metadata_file)
    if not records:
        log.error("No records built from {}", settings.paths.indian_seed_file)
        return 1
    paths = builder.write_outputs(records, out_dir)
    stats = builder.stats(records)
    _print(
        {
            "outputs": {fmt: str(path) for fmt, path in paths.items()},
            "stats": stats.model_dump(),
        }
    )
    if not do_import:
        return 0

    await container.mongo.connect()
    try:
        service = CompanyImportService(
            CompanyRepository(container.mongo.db), aliases=container.aliases
        )
        report = await service.import_file(paths["yaml"], ImportOptions(dry_run=dry_run))
        _print(report.model_dump())
        return 0 if report.validation.is_valid else 1
    finally:
        await container.mongo.disconnect()


def build_india_main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the Indian company career-site dataset (CSV/JSON/YAML[/Mongo])."
    )
    parser.add_argument("--out-dir", type=Path, default=Path("data/companies"))
    parser.add_argument("--import", dest="do_import", action="store_true", help="import to Mongo")
    parser.add_argument("--dry-run", action="store_true", help="with --import, write nothing")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(_build_india(args.out_dir, args.do_import, args.dry_run, args.verbose))
    )


# ---------------------------------------------------------------------------
# job-agent-embed  (Phase 8 — offline embedding generation)
# ---------------------------------------------------------------------------
async def _embed(force: bool, migrate: bool, limit: int, verbose: bool) -> int:
    from app.ai.job_service import EmbeddingMigrator, JobEmbeddingService
    from app.db.repositories.jobs import JobRepository

    _, container = _bootstrap(verbose)
    await container.mongo.connect()
    try:
        if not await container.mongo.ping():
            log.error("MongoDB not reachable — cannot embed")
            return 1
        repo = JobRepository(container.mongo.db)
        service = JobEmbeddingService(container.embedder, jobs=repo, metrics=container.metrics)
        if migrate:
            report = await EmbeddingMigrator(service, repo).migrate(limit=limit)
            _print({"migration": report.model_dump()})
        else:
            stats = await service.embed_stored(force=force, only_missing=not force, limit=limit)
            _print({"embedding": stats.model_dump()})
        return 0
    finally:
        await container.mongo.disconnect()


def embed_main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate embeddings for stored jobs offline (incremental by default)."
    )
    parser.add_argument("--force", action="store_true", help="re-embed all jobs")
    parser.add_argument(
        "--migrate", action="store_true", help="re-embed jobs whose model/version is stale"
    )
    parser.add_argument("--limit", type=int, default=100_000)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_embed(args.force, args.migrate, args.limit, args.verbose)))


# ---------------------------------------------------------------------------
# job-agent-list-collectors
# ---------------------------------------------------------------------------
def list_collectors_main() -> None:
    parser = argparse.ArgumentParser(description="List discovered collector plugins.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if args.verbose:
        settings.log_level = "DEBUG"
    configure_logging(settings)
    discover_collectors()
    _print([m.model_dump() for m in describe_all()])
