"""Dependency injection wiring for FastAPI.

A ``Container`` holds process-lifetime singletons (settings, Mongo manager,
metrics sink, cache, shared HTTP client) and lives on ``app.state``. The
``Depends(...)`` providers below expose them, and construct per-request
repositories/services from the shared DB handle. Construction stays explicit and
testable — override the container (or individual providers) in tests to inject
fakes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.ai.metrics import AiMetricsService
from app.ai.registry import ModelRegistry
from app.ai.resume_service import ResumeEmbeddingService
from app.ai.search import VectorSearchService
from app.analytics.service import AnalyticsService
from app.cache.base import CacheProvider
from app.cache.memory import InMemoryCache
from app.collectors.state import CollectorStateRegistry
from app.config.settings import Settings, VectorBackend, get_settings
from app.core.normalization.engine import NormalizationEngine
from app.core.quality import QualityScorer
from app.core.ranking.engine import RankingEngine
from app.db.mongo import MongoClientManager
from app.db.repositories.benchmarks import BenchmarkRepository
from app.db.repositories.companies import CompanyRepository
from app.db.repositories.config import ConfigRepository
from app.db.repositories.dead_letters import DeadLetterRepository
from app.db.repositories.import_history import ImportHistoryRepository
from app.db.repositories.jobs import JobRepository
from app.db.repositories.pipeline_runs import PipelineRunRepository
from app.db.repositories.reports import ReportHistoryRepository
from app.db.repositories.resume_embeddings import ResumeEmbeddingRepository
from app.db.repositories.runs import RunRepository
from app.db.repositories.user_preferences import UserPreferencesRepository
from app.db.repositories.users import UserRepository
from app.embeddings.cache import EmbeddingCache
from app.embeddings.factory import build_embedding_cache, build_embedding_provider
from app.embeddings.provider import EmbeddingProvider
from app.http.client import HttpClient, RateLimitedHttpClient
from app.importers.aliases import AliasResolver
from app.importers.service import CompanyImportService
from app.metrics.base import MetricsSink
from app.metrics.memory import InMemoryMetrics
from app.notifications.service import NotificationService
from app.notifications.smtp import SmtpNotifier
from app.pipeline.factory import build_filter_chain
from app.pipeline.pipeline import JobProcessingPipeline
from app.registry.reloader import RegistryReloader
from app.registry.service import SourceRegistry
from app.reports.dataset import ReportDatasetBuilder
from app.reports.service import ReportService
from app.routing.ats_updater import ATSMetadataUpdater
from app.routing.router import CompanyRouter
from app.services.config_service import ConfigService
from app.vector.atlas_scorer import AtlasVectorScorer
from app.vector.numpy_scorer import NumpyCosineScorer
from app.vector.scorer import VectorScorer


@dataclass
class Container:
    """Process-lifetime singletons, created in the app lifespan."""

    settings: Settings
    mongo: MongoClientManager
    metrics: MetricsSink
    cache: CacheProvider
    http: HttpClient
    sources: SourceRegistry
    aliases: AliasResolver
    collector_states: CollectorStateRegistry
    # Expensive, stateless pipeline components built once (taxonomies loaded here).
    normalizer: NormalizationEngine
    embedder: EmbeddingProvider
    # AI layer singletons (Phase 8).
    model_registry: ModelRegistry
    embedding_cache: EmbeddingCache
    reloader: RegistryReloader | None = None


def build_container(settings: Settings | None = None) -> Container:
    """Construct the container (called from the lifespan / app factory)."""

    settings = settings or get_settings()
    metrics = InMemoryMetrics()
    aliases = AliasResolver.from_file(settings.paths.company_aliases_file)
    # AI singletons: registry + embedding cache built once, shared by the
    # provider (so cache stats and model state are process-wide and consistent).
    model_registry = ModelRegistry()
    embedding_cache = build_embedding_cache(settings)
    embedder = build_embedding_provider(
        settings, registry=model_registry, metrics=metrics, cache=embedding_cache
    )
    return Container(
        settings=settings,
        mongo=MongoClientManager(settings),
        metrics=metrics,
        cache=InMemoryCache(),
        http=RateLimitedHttpClient(settings.http, metrics=metrics),
        sources=SourceRegistry(),
        aliases=aliases,
        collector_states=CollectorStateRegistry(),
        normalizer=NormalizationEngine.from_settings(settings, aliases=aliases),
        embedder=embedder,
        model_registry=model_registry,
        embedding_cache=embedding_cache,
    )


# ---- Core providers ---------------------------------------------------------
def get_container(request: Request) -> Container:
    return request.app.state.container


def get_app_settings(container: Annotated[Container, Depends(get_container)]) -> Settings:
    return container.settings


def get_database(
    container: Annotated[Container, Depends(get_container)],
) -> AsyncIOMotorDatabase:
    return container.mongo.db


def get_metrics(container: Annotated[Container, Depends(get_container)]) -> MetricsSink:
    return container.metrics


def get_cache(container: Annotated[Container, Depends(get_container)]) -> CacheProvider:
    return container.cache


def get_http_client(container: Annotated[Container, Depends(get_container)]) -> HttpClient:
    return container.http


def get_source_registry(
    container: Annotated[Container, Depends(get_container)],
) -> SourceRegistry:
    return container.sources


def get_collector_states(
    container: Annotated[Container, Depends(get_container)],
) -> CollectorStateRegistry:
    return container.collector_states


# ---- Repository providers (per-request, from the shared DB handle) ----------
DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_database)]


def get_job_repository(db: DbDep) -> JobRepository:
    return JobRepository(db)


def get_company_repository(db: DbDep) -> CompanyRepository:
    return CompanyRepository(db)


def get_user_repository(db: DbDep) -> UserRepository:
    return UserRepository(db)


def get_preferences_repository(db: DbDep) -> UserPreferencesRepository:
    return UserPreferencesRepository(db)


def get_config_repository(db: DbDep) -> ConfigRepository:
    return ConfigRepository(db)


def get_run_repository(db: DbDep) -> RunRepository:
    return RunRepository(db)


def get_dead_letter_repository(db: DbDep) -> DeadLetterRepository:
    return DeadLetterRepository(db)


def get_import_history_repository(db: DbDep) -> ImportHistoryRepository:
    return ImportHistoryRepository(db)


def get_benchmark_repository(db: DbDep) -> BenchmarkRepository:
    return BenchmarkRepository(db)


def get_config_service(
    db: DbDep,
    container: Annotated[Container, Depends(get_container)],
) -> ConfigService:
    return ConfigService(container.settings, ConfigRepository(db), container.cache)


def get_company_import_service(
    db: DbDep,
    container: Annotated[Container, Depends(get_container)],
) -> CompanyImportService:
    return CompanyImportService(
        CompanyRepository(db),
        dead_letters=DeadLetterRepository(db),
        history=ImportHistoryRepository(db),
        aliases=container.aliases,
    )


def get_company_router(
    container: Annotated[Container, Depends(get_container)],
) -> CompanyRouter:
    return CompanyRouter(container.sources)


def get_ats_updater(db: DbDep) -> ATSMetadataUpdater:
    return ATSMetadataUpdater(CompanyRepository(db))


def get_pipeline_run_repository(db: DbDep) -> PipelineRunRepository:
    return PipelineRunRepository(db)


def get_report_history_repository(db: DbDep) -> ReportHistoryRepository:
    return ReportHistoryRepository(db)


def get_analytics_service(db: DbDep) -> AnalyticsService:
    return AnalyticsService(
        JobRepository(db),
        runs=PipelineRunRepository(db),
        benchmarks=BenchmarkRepository(db),
    )


def get_report_service(
    db: DbDep,
    container: Annotated[Container, Depends(get_container)],
) -> ReportService:
    builder = ReportDatasetBuilder(
        JobRepository(db),
        get_analytics_service(db),
        runs=PipelineRunRepository(db),
        benchmarks=BenchmarkRepository(db),
    )
    return ReportService(
        builder,
        export_dir=container.settings.paths.export_dir,
        history=ReportHistoryRepository(db),
    )


def get_notifier(
    container: Annotated[Container, Depends(get_container)],
) -> SmtpNotifier:
    return SmtpNotifier(container.settings.smtp)


def get_notification_service(
    db: DbDep,
    container: Annotated[Container, Depends(get_container)],
) -> NotificationService:
    return NotificationService(get_report_service(db, container), get_notifier(container))


def get_pipeline(
    db: DbDep,
    container: Annotated[Container, Depends(get_container)],
) -> JobProcessingPipeline:
    """Assemble the pipeline from cached stateless engines + per-request repos."""

    return JobProcessingPipeline(
        normalizer=container.normalizer,
        filter_chain=build_filter_chain(container.settings),
        embedder=container.embedder,
        ranker=RankingEngine(container.settings.ranking),
        quality=QualityScorer(),
        aliases=container.aliases,
        jobs=JobRepository(db),
        runs=PipelineRunRepository(db),
    )


# ---- AI layer providers (Phase 8) -------------------------------------------
def get_model_registry(
    container: Annotated[Container, Depends(get_container)],
) -> ModelRegistry:
    return container.model_registry


def get_embedder(
    container: Annotated[Container, Depends(get_container)],
) -> EmbeddingProvider:
    return container.embedder


def get_embedding_cache(
    container: Annotated[Container, Depends(get_container)],
) -> EmbeddingCache:
    return container.embedding_cache


def get_resume_embedding_repository(db: DbDep) -> ResumeEmbeddingRepository:
    return ResumeEmbeddingRepository(db)


def get_resume_embedding_service(
    db: DbDep,
    container: Annotated[Container, Depends(get_container)],
) -> ResumeEmbeddingService:
    return ResumeEmbeddingService(
        container.embedder,
        ResumeEmbeddingRepository(db),
        registry=container.model_registry,
    )


async def get_vector_scorer(
    db: DbDep,
    container: Annotated[Container, Depends(get_container)],
) -> VectorScorer:
    """Atlas ``$vectorSearch`` in production; numpy cosine over stored vectors otherwise."""

    settings = container.settings
    if settings.vector.backend is VectorBackend.ATLAS:
        return AtlasVectorScorer.from_settings(db, settings)
    repo = JobRepository(db)
    jobs = await repo.find({"embedding": {"$ne": None}}, limit=100_000)
    corpus = [(job.job_hash, job.embedding) for job in jobs if job.embedding]
    return NumpyCosineScorer(corpus)


async def get_vector_search_service(
    db: DbDep,
    container: Annotated[Container, Depends(get_container)],
) -> VectorSearchService:
    scorer = await get_vector_scorer(db, container)
    return VectorSearchService(
        container.embedder, scorer, JobRepository(db), metrics=container.metrics
    )


def get_ai_metrics_service(
    container: Annotated[Container, Depends(get_container)],
) -> AiMetricsService:
    return AiMetricsService(
        container.metrics,
        cache=container.embedding_cache,
        registry=container.model_registry,
        embedder=container.embedder,
    )


# ---- Convenient type aliases for route signatures ---------------------------
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
ContainerDep = Annotated[Container, Depends(get_container)]
MetricsDep = Annotated[MetricsSink, Depends(get_metrics)]
CacheDep = Annotated[CacheProvider, Depends(get_cache)]
HttpClientDep = Annotated[HttpClient, Depends(get_http_client)]
JobRepositoryDep = Annotated[JobRepository, Depends(get_job_repository)]
CompanyRepositoryDep = Annotated[CompanyRepository, Depends(get_company_repository)]
UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]
PreferencesRepositoryDep = Annotated[UserPreferencesRepository, Depends(get_preferences_repository)]
ConfigServiceDep = Annotated[ConfigService, Depends(get_config_service)]
RunRepositoryDep = Annotated[RunRepository, Depends(get_run_repository)]
DeadLetterRepositoryDep = Annotated[DeadLetterRepository, Depends(get_dead_letter_repository)]
ImportHistoryRepositoryDep = Annotated[
    ImportHistoryRepository, Depends(get_import_history_repository)
]
BenchmarkRepositoryDep = Annotated[BenchmarkRepository, Depends(get_benchmark_repository)]
PipelineDep = Annotated[JobProcessingPipeline, Depends(get_pipeline)]
PipelineRunRepositoryDep = Annotated[PipelineRunRepository, Depends(get_pipeline_run_repository)]
ReportHistoryRepositoryDep = Annotated[
    ReportHistoryRepository, Depends(get_report_history_repository)
]
AnalyticsServiceDep = Annotated[AnalyticsService, Depends(get_analytics_service)]
ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]
NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]
# AI layer (Phase 8).
ModelRegistryDep = Annotated[ModelRegistry, Depends(get_model_registry)]
EmbedderDep = Annotated[EmbeddingProvider, Depends(get_embedder)]
EmbeddingCacheDep = Annotated[EmbeddingCache, Depends(get_embedding_cache)]
ResumeEmbeddingServiceDep = Annotated[
    ResumeEmbeddingService, Depends(get_resume_embedding_service)
]
VectorSearchServiceDep = Annotated[VectorSearchService, Depends(get_vector_search_service)]
AiMetricsServiceDep = Annotated[AiMetricsService, Depends(get_ai_metrics_service)]
