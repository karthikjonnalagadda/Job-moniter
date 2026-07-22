"""Shared value objects reused across domain models.

Small, immutable-ish building blocks (location, salary) so ``Job``, ``Company``,
and preferences agree on shape. Kept separate to avoid circular imports.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.base import AppBaseModel
from app.models.enums import SeniorityLevel, WorkMode

# Single-tenant default. Every user-scoped record defaults to this until real
# authentication assigns per-user ids (see app/models/user.py).
DEFAULT_USER_ID = "default"

# Version of the normalized Job schema. Stamped on every Job so consumers can
# evolve without forcing a migration on every record (schema versioning).
# v2 (Phase 6): universal schema — experience/employment/skills/quality/canonical.
# v3 (Phase 8): adds ``embedding_meta`` (model/version/hash provenance).
JOB_SCHEMA_VERSION = 3

# Version of the embedding format/pipeline. Bumped when the embedding
# construction changes so stale vectors can be detected and re-generated.
EMBEDDING_VERSION = 1


class Location(AppBaseModel):
    """Normalised location for a posting or preference."""

    raw: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    work_mode: WorkMode = WorkMode.UNKNOWN
    is_remote: bool = False


class SalaryRange(AppBaseModel):
    """Optional compensation range parsed from a posting."""

    min_amount: float | None = None
    max_amount: float | None = None
    currency: str | None = None
    period: str | None = None  # "year" | "month" | "hour"
    raw: str | None = None  # original text, for audit


class ExperienceRequirement(AppBaseModel):
    """Normalised experience requirement parsed from a posting."""

    min_years: float | None = None
    max_years: float | None = None
    level: SeniorityLevel = SeniorityLevel.UNKNOWN
    raw: str | None = None


class EmbeddingMeta(AppBaseModel):
    """Provenance for a stored embedding vector.

    Lets consumers know *which* model/version produced a vector and detect stale
    embeddings by comparing ``content_hash`` against the current content — the
    basis for incremental re-embedding (embed once; skip if unchanged).
    """

    model_name: str = "hashing"
    embedding_version: int = EMBEDDING_VERSION
    dimensions: int = 0
    content_hash: str | None = None
    generated_at: datetime | None = None


class QualityScore(AppBaseModel):
    """Processing-confidence breakdown for a normalised job (0-1 each)."""

    parser: float = 1.0  # how cleanly the raw payload parsed
    normalization: float = 1.0  # confidence of role/location/salary/etc. mapping
    duplicate: float = 1.0  # 1 - duplicate_confidence (1 = surely unique)
    collector: float = 1.0  # trust in the source collector
    completeness: float = 1.0  # fraction of key fields populated
    overall: float = 1.0  # weighted overall quality
    missing_fields: list[str] = Field(default_factory=list)
