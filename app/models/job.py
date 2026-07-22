"""Job posting model — the central persisted entity.

Holds the normalised posting, its 384-dim ``embedding`` (indexed by Atlas Vector
Search on ``jobs.embedding``), the composite ``MatchDetail`` breakdown, and the
``run_id``/``correlation_id`` that produced it for end-to-end traceability.
``job_hash`` is the unique dedup key.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.base import AppBaseModel, MongoDocument, PyObjectId
from app.models.common import (
    DEFAULT_USER_ID,
    JOB_SCHEMA_VERSION,
    EmbeddingMeta,
    ExperienceRequirement,
    Location,
    QualityScore,
    SalaryRange,
)
from app.models.enums import (
    ATSType,
    EmploymentType,
    JobStatus,
    SeniorityLevel,
    SourceType,
    WorkMode,
)


class MatchDetail(AppBaseModel):
    """Per-component breakdown of the composite Overall Score (0-100)."""

    score: float = 0.0  # weighted overall
    similarity: float = 0.0
    skill: float = 0.0
    experience: float = 0.0
    location: float = 0.0
    company_priority: float = 0.0
    freshness: float = 0.0
    quality: float = 0.0  # job quality sub-score (7th hybrid factor, Phase 8)
    # Explainable-AI: human-readable rationale per component + matched/missing.
    explanations: dict[str, str] = Field(default_factory=dict)
    narrative: str = ""  # one-line natural-language summary of the match
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    resume_id: str | None = None  # which resume version produced this ranking


class Job(MongoDocument):
    """A normalised, deduplicated, (eventually) ranked job posting.

    This is the **universal canonical schema** (v2): every collector normalises
    into this one immutable shape. New optional fields are additive; the
    ``schema_version`` lets consumers evolve without a forced migration.
    """

    schema_version: int = JOB_SCHEMA_VERSION  # normalized-Job schema version
    collector_version: str | None = None  # version of the collector that produced it
    job_hash: str  # unique dedup key (company+role+location+apply URL)
    content_fingerprint: str | None = None  # dedup layer 2 (content hash)
    external_id: str
    source: str  # collector name, e.g. "greenhouse"
    source_type: SourceType = SourceType.ATS
    ats_type: ATSType = ATSType.UNKNOWN

    company_id: PyObjectId | None = None
    company_name: str
    canonical_company_name: str | None = None  # after alias resolution
    company_slug: str | None = None
    company_aliases: list[str] = Field(default_factory=list)

    role: str
    normalized_role: str | None = None  # canonical role from the taxonomy
    description: str | None = None
    url: str  # the apply/posting URL
    career_url: str | None = None  # the company's career page (fallback source)
    location: Location = Field(default_factory=Location)
    country: str | None = None
    salary: SalaryRange | None = None
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    experience: ExperienceRequirement = Field(default_factory=ExperienceRequirement)
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN
    work_mode: WorkMode = WorkMode.UNKNOWN
    location_tags: list[str] = Field(default_factory=list)  # vector-search filter field
    posted_date: datetime | None = None

    # Extracted content.
    skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    status: JobStatus = JobStatus.NEW
    embedding: list[float] | None = None  # 384-dim; Atlas vectorSearch path
    embedding_meta: EmbeddingMeta | None = None  # model/version/hash provenance
    match: MatchDetail | None = None
    quality: QualityScore = Field(default_factory=QualityScore)
    confidence_score: float = 1.0  # overall processing confidence (mirrors quality.overall)

    # Auth-ready + traceability.
    user_id: str = DEFAULT_USER_ID
    run_id: str | None = None
    correlation_id: str | None = None
