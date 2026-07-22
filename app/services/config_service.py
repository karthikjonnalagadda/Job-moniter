"""Effective-configuration service (DB over env, with validation).

Resolution order:

1. Start from environment defaults (``Settings``) — always available.
2. If a config document exists in MongoDB, overlay it (runtime-updatable
   without redeploy).
3. Validate the result (ranking weights must sum to 1.0 — enforced by the
   ``RankingWeights`` model).

Falls back safely to the env baseline if the database is unreachable or holds an
invalid document, logging the reason — configuration must never break startup.
Results are cached briefly via the ``CacheProvider`` so hot paths don't re-read
the database on every call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config.logging import get_logger
from app.models.app_config import (
    NotificationPreferences,
    RankingWeights,
    SchedulerConfig,
)
from app.models.base import AppBaseModel
from app.models.common import DEFAULT_USER_ID

if TYPE_CHECKING:
    from app.cache.base import CacheProvider
    from app.config.settings import Settings
    from app.db.repositories.config import ConfigRepository

log = get_logger("api")

_CACHE_KEY = "effective_config:{user_id}"
_CACHE_TTL = 30.0  # seconds


class EffectiveConfig(AppBaseModel):
    """The merged, validated configuration the application actually runs on."""

    ranking: RankingWeights
    enabled_collectors: dict[str, bool]
    scheduler: SchedulerConfig
    notifications: NotificationPreferences
    feature_flags: dict[str, bool]
    source: str  # "database" | "environment"

    def feature_enabled(self, flag: str, *, default: bool = False) -> bool:
        return self.feature_flags.get(flag, default)


class ConfigService:
    """Resolves effective configuration from DB with an environment fallback."""

    def __init__(
        self,
        settings: Settings,
        repo: ConfigRepository | None = None,
        cache: CacheProvider | None = None,
    ) -> None:
        self._settings = settings
        self._repo = repo
        self._cache = cache

    def _from_env(self) -> EffectiveConfig:
        r = self._settings.ranking
        return EffectiveConfig(
            ranking=RankingWeights(
                weight_similarity=r.weight_similarity,
                weight_skill=r.weight_skill,
                weight_experience=r.weight_experience,
                weight_location=r.weight_location,
                weight_company_priority=r.weight_company_priority,
                weight_freshness=r.weight_freshness,
                weight_quality=r.weight_quality,
                min_score=r.min_score,
            ),
            enabled_collectors={},
            scheduler=SchedulerConfig(),
            notifications=NotificationPreferences(
                email_enabled=bool(self._settings.smtp.to_address)
            ),
            feature_flags={},
            source="environment",
        )

    async def load(self, *, user_id: str = DEFAULT_USER_ID) -> EffectiveConfig:
        """Return the effective config: DB document overlaid on env defaults."""

        cache_key = _CACHE_KEY.format(user_id=user_id)
        if self._cache is not None:
            cached = await self._cache.get(cache_key)
            if isinstance(cached, EffectiveConfig):
                return cached

        effective = await self._resolve(user_id)

        if self._cache is not None:
            await self._cache.set(cache_key, effective, ttl_seconds=_CACHE_TTL)
        return effective

    async def _resolve(self, user_id: str) -> EffectiveConfig:
        base = self._from_env()
        if self._repo is None:
            return base
        try:
            doc = await self._repo.get_active(user_id=user_id)
        except Exception as exc:  # DB issues must not break config resolution
            log.warning("Config DB read failed, using environment defaults: {}", exc)
            return base
        if doc is None:
            return base
        try:
            return EffectiveConfig(
                ranking=doc.ranking,  # RankingWeights validator already enforces sum=1.0
                enabled_collectors=doc.enabled_collectors,
                scheduler=doc.scheduler,
                notifications=doc.notifications,
                feature_flags=doc.feature_flags,
                source="database",
            )
        except ValueError as exc:
            log.warning("Stored config invalid, using environment defaults: {}", exc)
            return base

    async def invalidate(self, *, user_id: str = DEFAULT_USER_ID) -> None:
        if self._cache is not None:
            await self._cache.delete(_CACHE_KEY.format(user_id=user_id))
