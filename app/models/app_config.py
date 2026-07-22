"""Versioned application configuration stored in MongoDB.

Environment variables remain the source of *bootstrap* configuration. This
document layers **runtime-updatable** configuration on top: when a config
document exists it overrides the corresponding env defaults (merged by
``app.services.config_service.ConfigService``), enabling changes without a
redeploy. Each save bumps ``version`` for auditability and optimistic updates.

Stored here per the Phase-2 enhancement: ranking weights, enabled collectors,
scheduler configuration, notification preferences, and feature flags.
"""

from __future__ import annotations

import math

from pydantic import Field, model_validator

from app.models.base import AppBaseModel, MongoDocument
from app.models.common import DEFAULT_USER_ID


class RankingWeights(AppBaseModel):
    """Composite-score weights (must sum to 1.0). Mirrors ``RankingSettings``."""

    weight_similarity: float = 0.34
    weight_skill: float = 0.24
    weight_experience: float = 0.14
    weight_location: float = 0.10
    weight_company_priority: float = 0.10
    weight_freshness: float = 0.03
    weight_quality: float = 0.05
    min_score: int = 70

    @model_validator(mode="after")
    def _sum_to_one(self) -> RankingWeights:
        total = (
            self.weight_similarity
            + self.weight_skill
            + self.weight_experience
            + self.weight_location
            + self.weight_company_priority
            + self.weight_freshness
            + self.weight_quality
        )
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(f"Ranking weights must sum to 1.0, got {total:.4f}")
        return self


class SchedulerConfig(AppBaseModel):
    """Daily-run scheduling knobs (informational; cron lives in GitHub Actions)."""

    enabled: bool = True
    cron: str = "30 0 * * *"  # 06:00 IST
    timezone: str = "Asia/Kolkata"
    max_retries: int = 2


class NotificationPreferences(AppBaseModel):
    """Which channels fire and the score threshold to notify at."""

    email_enabled: bool = True
    enabled_channels: list[str] = Field(default_factory=lambda: ["smtp"])
    min_score_to_notify: int = 70


class AppConfigDocument(MongoDocument):
    """The single active configuration document (per user in future)."""

    user_id: str = DEFAULT_USER_ID
    key: str = "global"
    version: int = 1
    ranking: RankingWeights = Field(default_factory=RankingWeights)
    enabled_collectors: dict[str, bool] = Field(default_factory=dict)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    notifications: NotificationPreferences = Field(default_factory=NotificationPreferences)
    feature_flags: dict[str, bool] = Field(default_factory=dict)
