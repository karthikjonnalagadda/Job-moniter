"""Shared enumerations. Central so collectors, models, and services agree."""

from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
    CAREER_SITE = "career_site"
    ATS = "ats"
    JOB_BOARD = "job_board"


class ATSType(StrEnum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKDAY = "workday"
    SMARTRECRUITERS = "smartrecruiters"
    BAMBOOHR = "bamboohr"
    TEAMTAILOR = "teamtailor"
    RECRUITEE = "recruitee"
    JOBVITE = "jobvite"
    ICIMS = "icims"
    ORACLE = "oracle"
    SUCCESSFACTORS = "successfactors"
    COMEET = "comeet"
    BREEZYHR = "breezyhr"
    JAZZHR = "jazzhr"
    UNKNOWN = "unknown"


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class EmploymentType(StrEnum):
    """Nature of the engagement (normalised from free-text posting fields)."""

    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    APPRENTICESHIP = "apprenticeship"
    GRADUATE_PROGRAM = "graduate_program"
    UNKNOWN = "unknown"


class SeniorityLevel(StrEnum):
    FRESHER = "fresher"
    ENTRY = "entry"
    JUNIOR = "junior"
    ASSOCIATE = "associate"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    UNKNOWN = "unknown"


class JobStatus(StrEnum):
    NEW = "new"
    REPORTED = "reported"
    APPLIED = "applied"
    ARCHIVED = "archived"


class ApplicationStatus(StrEnum):
    """Lifecycle of a user's application to a job (future Application Tracker)."""

    NOT_APPLIED = "not_applied"
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class HiringTrend(StrEnum):
    GROWING = "growing"
    STABLE = "stable"
    SLOWING = "slowing"
    FROZEN = "frozen"
    UNKNOWN = "unknown"


class HiringCategory(StrEnum):
    """Coarse hiring-intensity bucket for prioritisation."""

    AGGRESSIVE = "aggressive"
    ACTIVE = "active"
    MODERATE = "moderate"
    OCCASIONAL = "occasional"
    UNKNOWN = "unknown"


class CompanyCategory(StrEnum):
    """Business/sector classification of a company (used for import stats)."""

    IT_SERVICES = "it_services"
    PRODUCT = "product"
    STARTUP = "startup"
    UNICORN = "unicorn"
    SAAS = "saas"
    FINTECH = "fintech"
    EDTECH = "edtech"
    HEALTHTECH = "healthtech"
    ECOMMERCE = "ecommerce"
    ANALYTICS_AI = "analytics_ai"
    CONSULTING = "consulting"
    BFSI = "bfsi"
    MANUFACTURING = "manufacturing"
    AUTOMOTIVE = "automotive"
    TELECOM = "telecom"
    ENERGY = "energy"
    RETAIL = "retail"
    PHARMA = "pharma"
    CONGLOMERATE = "conglomerate"
    OTHER = "other"
    UNKNOWN = "unknown"


class CrawlFrequency(StrEnum):
    """How often a company's career source should be polled."""

    DAILY = "daily"
    TWICE_DAILY = "twice_daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    MANUAL = "manual"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class UserRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    VIEWER = "viewer"


class LegalMode(StrEnum):
    """How a collector obtains data — governs whether it may run by default."""

    API = "api"
    FEED = "feed"
    SCRAPE = "scrape"  # opt-in only; disabled by default (e.g. LinkedIn)


class RunStage(StrEnum):
    COLLECT = "collect"
    NORMALIZE = "normalize"
    DEDUPLICATE = "deduplicate"
    RANK = "rank"
    STORE = "store"
    EXPORT = "export"
    EMAIL = "email"
