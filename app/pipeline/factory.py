"""Construct a ``JobProcessingPipeline`` from settings + repositories."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.filters.chain import FilterChain
from app.core.filters.experience import ExperienceFilter
from app.core.filters.freshness import FreshnessFilter
from app.core.filters.location import LocationFilter
from app.core.filters.role_relevance import RoleRelevanceFilter
from app.core.filters.seniority import SeniorityTitleFilter
from app.core.normalization.engine import NormalizationEngine
from app.core.quality import QualityScorer
from app.core.ranking.engine import RankingEngine
from app.embeddings.factory import build_embedding_provider
from app.pipeline.pipeline import JobProcessingPipeline

if TYPE_CHECKING:
    from app.config.settings import Settings
    from app.db.repositories.jobs import JobRepository
    from app.db.repositories.pipeline_runs import PipelineRunRepository
    from app.importers.aliases import AliasResolver


def build_filter_chain(
    settings: Settings, *, allowed_locations: list[str] | None = None
) -> FilterChain:
    """Ordered filter chain (AND semantics), all applied before embedding/ranking.

    Relevance and seniority run first so unrelated/senior postings are dropped
    cheaply, then experience/freshness/location gates.
    """

    filters: list = []
    # Seniority first (cheapest, highest-volume rejects), then role relevance,
    # then experience/freshness/location — matching the filtering-waterfall report.
    if settings.filters.enable_seniority_filter:
        filters.append(
            SeniorityTitleFilter(max_years=settings.filters.max_experience_years)
        )
    if settings.filters.enable_role_filter:
        filters.append(RoleRelevanceFilter())
    filters.extend(
        [
            ExperienceFilter(
                max_years=settings.filters.max_experience_years,
                allow_if_entry_level=settings.filters.allow_if_entry_level,
            ),
            FreshnessFilter(max_age_hours=settings.filters.max_age_hours),
            LocationFilter(allowed=allowed_locations),
        ]
    )
    return FilterChain(filters)


def build_pipeline(
    settings: Settings,
    *,
    aliases: AliasResolver | None = None,
    jobs: JobRepository | None = None,
    runs: PipelineRunRepository | None = None,
    allowed_locations: list[str] | None = None,
) -> JobProcessingPipeline:
    """Wire the full pipeline. Embedding backend comes from settings (hashing)."""

    return JobProcessingPipeline(
        normalizer=NormalizationEngine.from_settings(settings, aliases=aliases),
        filter_chain=build_filter_chain(settings, allowed_locations=allowed_locations),
        embedder=build_embedding_provider(settings),
        ranker=RankingEngine(settings.ranking),
        quality=QualityScorer(),
        aliases=aliases,
        jobs=jobs,
        runs=runs,
    )
