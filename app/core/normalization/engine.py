"""Normalization engine — ``RawJob`` → canonical ``Job`` (the universal schema).

Orchestrates every field-level normalizer (role, location, salary, experience,
employment type, freshness, skills) plus company-alias resolution and dedup
hashing, and computes a normalization-confidence signal that feeds the quality
score. This is the single place a collector's loose output becomes the immutable
canonical ``Job``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.dedup.hashing import content_fingerprint, job_hash
from app.core.normalization.employment import EmploymentNormalizer
from app.core.normalization.experience import ExperienceNormalizer
from app.core.normalization.freshness import FreshnessParser
from app.core.normalization.location import LocationNormalizer
from app.core.normalization.roles import RoleNormalizer
from app.core.normalization.salary import SalaryNormalizer
from app.core.quality import QualityScorer
from app.core.skills.extractor import SkillExtractor
from app.models.common import DEFAULT_USER_ID
from app.models.enums import ATSType, EmploymentType, SeniorityLevel, SourceType
from app.models.job import Job

if TYPE_CHECKING:
    from app.collectors.base import RawJob
    from app.config.settings import Settings
    from app.importers.aliases import AliasResolver


def job_text(job: Job) -> str:
    """Canonical text used to embed a job (role + skills + description)."""

    parts = [
        job.normalized_role or job.role,
        " ".join(job.skills),
        " ".join(job.technologies),
        job.description or "",
    ]
    return " ".join(p for p in parts if p).strip()


class NormalizationEngine:
    """Turns a ``RawJob`` into a fully-normalised canonical ``Job``."""

    def __init__(
        self,
        *,
        roles: RoleNormalizer,
        locations: LocationNormalizer,
        salary: SalaryNormalizer,
        experience: ExperienceNormalizer,
        employment: EmploymentNormalizer,
        freshness: FreshnessParser,
        skills: SkillExtractor,
        aliases: AliasResolver | None = None,
        quality: QualityScorer | None = None,
    ) -> None:
        self._roles = roles
        self._locations = locations
        self._salary = salary
        self._experience = experience
        self._employment = employment
        self._freshness = freshness
        self._skills = skills
        self._aliases = aliases
        self._quality = quality or QualityScorer()

    @property
    def skills(self) -> SkillExtractor:
        """The skill extractor (reused by the pipeline's extract-skills path)."""

        return self._skills

    @classmethod
    def from_settings(
        cls, settings: Settings, *, aliases: AliasResolver | None = None
    ) -> NormalizationEngine:
        base = settings.paths.taxonomies_dir
        return cls(
            roles=RoleNormalizer.from_file(base / "roles.yaml"),
            locations=LocationNormalizer.from_file(base / "locations.yaml"),
            salary=SalaryNormalizer(),
            experience=ExperienceNormalizer(),
            employment=EmploymentNormalizer(),
            freshness=FreshnessParser(),
            skills=SkillExtractor.from_file(base / "skills.yaml"),
            aliases=aliases,
        )

    def normalize(
        self,
        raw: RawJob,
        *,
        source: str,
        source_type: SourceType = SourceType.ATS,
        ats_type: ATSType = ATSType.UNKNOWN,
        collector_version: str | None = None,
        career_url: str | None = None,
        parser_confidence: float = 1.0,
        collector_confidence: float = 1.0,
        user_id: str = DEFAULT_USER_ID,
        run_id: str | None = None,
        correlation_id: str | None = None,
    ) -> Job:
        payload: dict[str, Any] = raw.raw if isinstance(raw.raw, dict) else {}
        title = raw.title
        description = raw.description

        normalized_role = self._roles.normalize(title)
        location = self._locations.normalize(raw.location)
        location_tags = self._locations.tags(location)

        salary_text = _first_str(payload, ("salary", "compensation", "pay")) or description
        salary = self._salary.parse(salary_text)

        experience_text = _first_str(payload, ("experience", "experience_level")) or description
        experience = self._experience.parse(experience_text)

        employment_text = _first_str(payload, ("employment_type", "type", "commitment")) or title
        employment = self._employment.parse(f"{employment_text} {description or ''}")

        # Prefer a raw source date string (handles relative/epoch formats);
        # fall back to the collector's already-typed datetime.
        posted_raw = _first_str(
            payload, ("posted", "posted_date", "date", "published_at", "created_at", "updated_at")
        )
        posted = self._freshness.parse(posted_raw) or self._freshness.parse(raw.posted_at)
        extracted = self._skills.extract(title, description)

        canonical_name, aliases_list = self._resolve_company(raw.company)

        location_key = (location.city or "") + " " + (location.country or "")
        hash_key = job_hash(raw.company, normalized_role or title, location_key, raw.url)
        fingerprint = content_fingerprint(title, description)
        tags = list(location_tags)
        if employment != EmploymentType.UNKNOWN:
            tags.append(employment.value)

        job = Job(
            collector_version=collector_version,
            job_hash=hash_key,
            content_fingerprint=fingerprint,
            external_id=raw.external_id,
            source=source,
            source_type=source_type,
            ats_type=ats_type,
            company_name=raw.company,
            canonical_company_name=canonical_name,
            company_aliases=aliases_list,
            role=title,
            normalized_role=normalized_role,
            description=description,
            url=raw.url,
            career_url=career_url,
            location=location,
            country=location.country,
            salary=salary,
            employment_type=employment,
            experience=experience,
            seniority=experience.level,
            work_mode=location.work_mode,
            location_tags=location_tags,
            posted_date=posted,
            skills=extracted.skills,
            technologies=extracted.technologies,
            tags=_dedupe(tags),
            user_id=user_id,
            run_id=run_id,
            correlation_id=correlation_id,
        )

        confidence = self._normalization_confidence(
            job, role_matched=normalized_role is not None, extracted_any=bool(extracted.skills)
        )
        job.quality = self._quality.score(
            job,
            parser=parser_confidence,
            normalization=confidence,
            duplicate_confidence=0.0,
            collector=collector_confidence,
        )
        job.confidence_score = job.quality.overall
        return job

    def _resolve_company(self, name: str) -> tuple[str | None, list[str]]:
        if self._aliases is None:
            return None, []
        match = self._aliases.resolve(name)
        if match is None:
            return None, []
        canonical_slug, canonical_name = match
        aliases = [name] if _norm(name) != _norm(canonical_name) else []
        return canonical_name, aliases

    @staticmethod
    def _normalization_confidence(job: Job, *, role_matched: bool, extracted_any: bool) -> float:
        score = 1.0
        if not role_matched:
            score -= 0.15
        if not (job.location.city or job.location.country or job.location.is_remote):
            score -= 0.10
        if job.employment_type == EmploymentType.UNKNOWN:
            score -= 0.05
        if job.experience.min_years is None and job.experience.level == SeniorityLevel.UNKNOWN:
            score -= 0.05
        if not extracted_any:
            score -= 0.10
        return max(0.0, round(score, 4))


def _first_str(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
