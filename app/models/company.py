"""Company + company-intelligence models.

Designed for 10,000+ companies. The static registry fields (ATS wiring, career
URL, geography) and the derived ``CompanyIntelligence`` sub-document (hiring
signals) are kept together so a single lookup drives collection and ranking.
Seed data imports (CSV/JSON/YAML) map onto this model with no code change.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.base import AppBaseModel, MongoDocument
from app.models.enums import (
    ATSType,
    CompanyCategory,
    CrawlFrequency,
    HiringCategory,
    HiringTrend,
)


class CompanyIntelligence(AppBaseModel):
    """Derived hiring signals + crawl telemetry (populated by later phases)."""

    # ---- Hiring signals ----
    hiring_frequency: float | None = None  # openings observed per week
    ai_hiring_score: float | None = None  # 0-100, AI/ML hiring intensity
    average_openings: float | None = None
    average_jobs_per_week: float | None = None
    remote_hiring_percentage: float | None = None  # 0-100
    hiring_trend: HiringTrend = HiringTrend.UNKNOWN
    preferred_roles: list[str] = Field(default_factory=list)
    preferred_technologies: list[str] = Field(default_factory=list)
    company_priority_score: float | None = None  # 0-100 composite priority
    ats_platform: ATSType | None = None
    remote_support: bool | None = None

    # ---- Crawl telemetry ----
    last_successful_crawl: datetime | None = None
    crawl_failures: int = 0
    crawl_duration_seconds: float | None = None


class Company(MongoDocument):
    """A hiring company and how to collect from it."""

    name: str
    slug: str  # unique business key
    aliases: list[str] = Field(default_factory=list)  # alt names (Meta -> Facebook)
    canonical_slug: str | None = None  # set when this company folds into a parent
    ats_type: ATSType = ATSType.UNKNOWN
    ats_token: str | None = None  # board token / tenant id for the ATS API
    career_url: str | None = None
    career_platform: str | None = None  # human name of the hosting platform
    industry: str | None = None
    country: str | None = None
    headquarters: str | None = None
    company_category: CompanyCategory = CompanyCategory.UNKNOWN
    hiring_category: HiringCategory = HiringCategory.UNKNOWN
    priority_score: float | None = None  # 0-100 static collection priority
    ai_hiring_score: float | None = None
    remote_support: bool | None = None
    active_status: bool = True
    crawl_frequency: CrawlFrequency = CrawlFrequency.WEEKLY
    last_crawled: datetime | None = None
    supported_roles: list[str] = Field(default_factory=list)
    preferred_technologies: list[str] = Field(default_factory=list)
    notes: str | None = None
    intelligence: CompanyIntelligence = Field(default_factory=CompanyIntelligence)
