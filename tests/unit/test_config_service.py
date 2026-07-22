"""ConfigService: env fallback + DB override + validation."""

from __future__ import annotations

from app.config.settings import Settings
from app.db.repositories.config import ConfigRepository
from app.models.app_config import AppConfigDocument, RankingWeights
from app.services.config_service import ConfigService


async def test_env_fallback_without_repo() -> None:
    service = ConfigService(Settings())
    cfg = await service.load()
    assert cfg.source == "environment"
    assert cfg.ranking.weight_similarity == 0.34


async def test_db_overrides_env(mock_db) -> None:
    repo = ConfigRepository(mock_db)
    await repo.save(
        AppConfigDocument(
            ranking=RankingWeights(
                weight_similarity=0.50,
                weight_skill=0.20,
                weight_experience=0.10,
                weight_location=0.10,
                weight_company_priority=0.05,
                weight_freshness=0.05,
                weight_quality=0.0,
            ),
            feature_flags={"weekly_reports": True},
        )
    )
    service = ConfigService(Settings(), repo)
    cfg = await service.load()
    assert cfg.source == "database"
    assert cfg.ranking.weight_similarity == 0.50
    assert cfg.feature_enabled("weekly_reports") is True


async def test_invalid_weights_rejected() -> None:
    # RankingWeights enforces sum == 1.0 at construction.
    try:
        RankingWeights(weight_similarity=0.9, weight_skill=0.9)
    except ValueError:
        return
    raise AssertionError("expected ValueError for weights not summing to 1.0")
