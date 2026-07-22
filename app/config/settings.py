"""Typed application configuration.

All configuration enters the application through this module. Nothing else in
the codebase reads ``os.environ`` directly — that keeps configuration testable,
validated, and discoverable in exactly one place (Single Source of Truth).

Environment variables are prefixed ``JOBAGENT_`` and nested settings use a
``__`` delimiter, e.g. ``JOBAGENT_RANKING__WEIGHT_SIMILARITY=0.40`` maps to
``settings.ranking.weight_similarity``.
"""

from __future__ import annotations

import math
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class VectorBackend(StrEnum):
    ATLAS = "atlas"
    NUMPY = "numpy"


class EmbeddingProviderType(StrEnum):
    """Which embedding implementation to build behind the ``EmbeddingProvider`` port."""

    AUTO = "auto"  # sentence-transformers if importable, else hashing fallback
    SENTENCE_TRANSFORMER = "sentence_transformer"  # force production model
    HASHING = "hashing"  # force the dependency-light deterministic encoder


class EmbeddingCacheBackend(StrEnum):
    """Where content-hash → embedding pairs are cached."""

    MEMORY = "memory"
    MONGO = "mongo"
    REDIS = "redis"  # reserved — falls back to memory until a client is wired
    NONE = "none"


class DeviceType(StrEnum):
    """Compute device for the embedding model."""

    AUTO = "auto"  # cuda if available, else cpu
    CPU = "cpu"
    CUDA = "cuda"


# ---------------------------------------------------------------------------
# Nested setting groups
# ---------------------------------------------------------------------------
class MongoSettings(BaseModel):
    uri: SecretStr = Field(default=SecretStr("mongodb://localhost:27017"))
    db_name: str = "job_intelligence"
    max_pool_size: int = 20
    server_selection_timeout_ms: int = 5000


class VectorSettings(BaseModel):
    backend: VectorBackend = VectorBackend.ATLAS
    index_name: str = "jobs_vector_index"
    path: str = "embedding"  # document field holding the vector
    dimensions: int = 384
    similarity: str = "cosine"
    num_candidates: int = 200
    limit: int = 100
    score_threshold: float = 0.0  # drop results below this cosine score
    hybrid_alpha: float = 0.6  # weight of the semantic score in hybrid search (0-1)
    validate_on_startup: bool = True  # log a warning if the Atlas index is missing


class EmbeddingSettings(BaseModel):
    provider: EmbeddingProviderType = EmbeddingProviderType.AUTO
    model_name: str = "BAAI/bge-small-en-v1.5"
    device: DeviceType = DeviceType.AUTO
    normalize: bool = True
    batch_size: int = 32
    max_seq_length: int = 512
    quantize: bool = False  # int8 dynamic quantization for low-memory CPU hosts
    trust_remote_code: bool = False
    # Model lifecycle.
    download_if_missing: bool = True  # let the model auto-download on first load
    checksum: str = ""  # optional sha256 of the model dir manifest (empty = skip)
    fallback_to_hashing: bool = True  # degrade to hashing when the model is unavailable
    warmup: bool = True  # encode a dummy input on startup to pay import/load cost early
    # Caching.
    cache_backend: EmbeddingCacheBackend = EmbeddingCacheBackend.MEMORY
    cache_ttl_seconds: float | None = None  # None = no expiry
    # Memory-aware batching: cap on characters per inference batch (0 = disabled).
    max_batch_chars: int = 200_000
    # Applied to the resume (query) side only; encapsulated by EmbeddingProvider.
    query_instruction: str = (
        "Represent this resume for retrieving relevant job descriptions: "
    )

    model_config = SettingsConfigDict(protected_namespaces=())


class RankingSettings(BaseModel):
    """Weights for the composite Overall Score. Must sum to 1.0."""

    # Rebalanced for search-quality (v0.8.x): the semantic component is only as
    # good as the embedding backend, and on the hashing fallback it is weak, so it
    # is no longer dominant. Reliable deterministic signals (skill overlap,
    # experience fit, location, company priority, posting quality) carry more of
    # the composite for genuinely-filtered relevant jobs. Every weight stays
    # overridable via JOBAGENT_RANKING__WEIGHT_*. Must sum to 1.0.
    weight_similarity: float = 0.34
    weight_skill: float = 0.24
    weight_experience: float = 0.14
    weight_location: float = 0.10
    weight_company_priority: float = 0.10
    weight_freshness: float = 0.03
    weight_quality: float = 0.05
    min_score: int = 70

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> RankingSettings:
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
            raise ValueError(
                f"Ranking weights must sum to 1.0, got {total:.4f}. "
                "Adjust JOBAGENT_RANKING__WEIGHT_* variables."
            )
        return self


class FilterSettings(BaseModel):
    max_age_hours: int = 24
    max_experience_years: int = 2
    allow_if_entry_level: bool = True
    # Search-quality gates (v0.8.x). Reject unrelated functions and senior titles
    # in the filter stage — i.e. before embedding/ranking — so they never reach
    # the vector or ranking stages. Both default on; disable via
    # JOBAGENT_FILTERS__ENABLE_ROLE_FILTER / __ENABLE_SENIORITY_FILTER.
    enable_role_filter: bool = True
    enable_seniority_filter: bool = True


class SmtpSettings(BaseModel):
    host: str = "localhost"
    port: int = 587
    username: str = ""
    password: SecretStr = SecretStr("")
    use_tls: bool = True
    from_address: str = "AI Job Agent <noreply@example.com>"
    to_address: str = ""


class HttpSettings(BaseModel):
    user_agent: str = "AIJobIntelligenceAgent/2026 (+https://example.com/bot)"
    timeout_seconds: float = 20.0
    max_retries: int = 3
    default_rate_limit_rps: float = 2.0


class CollectorSettings(BaseModel):
    """Collector execution knobs (Phase 5)."""

    archive_raw: bool = False  # store raw upstream payloads
    raw_retention_days: int = 14  # TTL for archived payloads
    max_pages: int = 50  # pagination safety cap per target
    incremental: bool = True  # use SyncState conditional fetching when possible
    # ---- performance budgets (SLA warnings) ----
    budget_response_ms: float = 5000.0  # per-request avg response time
    budget_max_crawl_seconds: float = 120.0  # per-collector run wall time
    budget_import_min_rps: float = 50.0  # min import throughput (rows/sec)


class PathSettings(BaseModel):
    ats_sources_file: Path = Path("data/ats_sources.yaml")
    company_aliases_file: Path = Path("data/company_aliases.yaml")
    companies_seed_file: Path = Path("data/companies/companies.csv")
    companies_dir: Path = Path("data/companies")
    taxonomies_dir: Path = Path("data/taxonomies")  # role/location/skill taxonomies
    # Indian company career-site seed list + expanded curated metadata.
    indian_seed_file: Path = Path("data/companies/Indian_Company_Career_Sites.csv")
    indian_metadata_file: Path = Path("data/companies/indian_company_metadata.yaml")
    resume_file: Path = Path("data/resume/resume.txt")
    export_dir: Path = Path("exports")


# ---------------------------------------------------------------------------
# Root settings
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    app_name: str = "AI Job Intelligence Agent"
    env: Environment = Environment.DEVELOPMENT
    debug: bool = True
    log_level: str = "INFO"
    log_json: bool = False
    log_dir: Path = Path("logs")
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # Seconds between source-registry hot-reload checks (0 disables the watcher).
    registry_reload_seconds: int = 0

    mongo: MongoSettings = Field(default_factory=MongoSettings)
    vector: VectorSettings = Field(default_factory=VectorSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    ranking: RankingSettings = Field(default_factory=RankingSettings)
    filters: FilterSettings = Field(default_factory=FilterSettings)
    smtp: SmtpSettings = Field(default_factory=SmtpSettings)
    http: HttpSettings = Field(default_factory=HttpSettings)
    collector: CollectorSettings = Field(default_factory=CollectorSettings)
    paths: PathSettings = Field(default_factory=PathSettings)

    model_config = SettingsConfigDict(
        env_prefix="JOBAGENT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def is_production(self) -> bool:
        return self.env is Environment.PRODUCTION

    @model_validator(mode="after")
    def _cross_field_checks(self) -> Settings:
        # Embedding dimension must match the configured vector index dimension.
        if self.vector.dimensions <= 0:
            raise ValueError("vector.dimensions must be positive")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide singleton Settings instance.

    Cached so the ``.env`` file and environment are parsed exactly once. Tests
    can call ``get_settings.cache_clear()`` to force a reload.
    """

    return Settings()
