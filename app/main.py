"""FastAPI application factory + lifecycle.

``create_app()`` builds the app: configures logging, constructs the DI
container, registers exception handlers and routes, and manages the
startup/shutdown lifecycle via an async lifespan (connect Mongo on startup,
close on shutdown).

Run locally:  ``uvicorn app.main:app --reload``
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.deps import Container, build_container
from app.api.middleware import CorrelationIdMiddleware
from app.api.router import api_router
from app.collectors.loader import discover_collectors
from app.config.logging import configure_logging, get_logger
from app.config.settings import Settings, get_settings
from app.core.exceptions import JobAgentError
from app.db.indexes import ensure_standard_indexes
from app.registry.loaders import MongoSourceLoader, YamlSourceLoader
from app.registry.reloader import RegistryReloader

log = get_logger("api")


async def _load_source_registry(container: Container) -> None:
    """Populate the source registry from YAML, overlaid by Mongo when reachable."""

    settings = container.settings
    try:
        yaml_path = settings.paths.ats_sources_file
        if yaml_path.exists():
            await container.sources.load_from(YamlSourceLoader(yaml_path))
        if container.mongo.db is not None:
            try:
                await container.sources.load_from(MongoSourceLoader(container.mongo.db))
            except Exception as exc:  # Mongo overlay is optional
                log.debug("Mongo source overlay skipped: {}", exc)
    except Exception as exc:  # registry load must not crash startup
        log.error("Source registry load failed: {}", exc)


async def _warmup_embeddings(container: Container) -> None:
    """Pre-load / warm the embedding model (non-fatal; skipped when disabled)."""

    if not container.settings.embedding.warmup:
        return
    try:
        await container.embedder.warmup()
    except Exception as exc:  # warm-up is best-effort
        log.warning("Embedding warm-up skipped: {}", exc)


async def _validate_vector_index(container: Container) -> None:
    """Log a warning if the Atlas vector index is missing (never blocks startup)."""

    settings = container.settings
    if not settings.vector.validate_on_startup or settings.vector.backend.value != "atlas":
        return
    try:
        from app.vector.atlas_scorer import AtlasVectorScorer

        scorer = AtlasVectorScorer.from_settings(container.mongo.db, settings)
        if await scorer.validate_index():
            log.info("Atlas vector index '{}' present", settings.vector.index_name)
        else:
            log.warning(
                "Atlas vector index '{}' not found — run job-agent-bootstrap or create it "
                "in Atlas (vector search will return no results until then)",
                settings.vector.index_name,
            )
    except Exception as exc:  # validation is advisory only
        log.debug("Vector index validation skipped: {}", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: connect dependencies. Shutdown: release them."""

    container = app.state.container
    settings: Settings = container.settings
    log.info("Starting {} [env={}]", settings.app_name, settings.env)
    try:
        await container.mongo.connect()
        # Verify connectivity early; log (don't crash) so /health can report it.
        if await container.mongo.ping():
            log.info("MongoDB reachable")
            # Idempotent index creation; resilient (never blocks startup).
            await ensure_standard_indexes(container.mongo.db)
            await _validate_vector_index(container)
        else:
            log.warning("MongoDB not reachable at startup — running degraded")
    except Exception as exc:  # startup must be observable, not fatal
        log.error("Startup dependency error: {}", exc)

    # Warm up the embedding model so the first real request doesn't pay load cost.
    await _warmup_embeddings(container)

    # Load the source registry (YAML baseline + optional Mongo overlay).
    await _load_source_registry(container)
    log.info("Source registry: {} sources loaded", len(container.sources))

    # Optional hot-reload watcher for ats_sources.yaml edits.
    container.reloader = RegistryReloader(
        container.sources,
        settings.paths.ats_sources_file,
        settings.registry_reload_seconds,
    )
    container.reloader.start()

    yield

    log.info("Shutting down {}", settings.app_name)
    if container.reloader is not None:
        await container.reloader.stop()
    await container.http.aclose()
    await container.mongo.disconnect()


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(JobAgentError)
    async def _handle_domain_error(_: Request, exc: JobAgentError) -> ORJSONResponse:
        log.warning("Domain error [{}]: {}", exc.code, exc.message)
        return ORJSONResponse(
            status_code=exc.http_status,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    # Auto-discover collector plugins so the registry is populated before any
    # request (idempotent; imports each plugin module once).
    discover_collectors()

    app = FastAPI(
        title=settings.app_name,
        version="0.8.0",
        default_response_class=ORJSONResponse,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    # Container lives on app.state for the whole process lifetime.
    app.state.container = build_container(settings)

    # Correlation id is established first (outermost) so every log line — including
    # CORS/errors — carries it.
    app.add_middleware(CorrelationIdMiddleware)
    # Explicit allowlist wins; otherwise allow-all in debug, deny cross-origin in prod.
    cors_origins = settings.cors_origins or (["*"] if settings.debug else [])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_exception_handlers(app)
    app.include_router(api_router)
    return app


# ASGI entrypoint for uvicorn / gunicorn.
app = create_app()
