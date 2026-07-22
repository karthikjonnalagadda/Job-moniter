"""Flatten a canonical ``Job`` into a tabular row (shared by CSV/JSON/Excel)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.job import Job

# Ordered columns for tabular exports.
COLUMNS: tuple[str, ...] = (
    "company",
    "canonical_company",
    "role",
    "normalized_role",
    "location",
    "work_mode",
    "country",
    "employment_type",
    "experience_min_years",
    "experience_max_years",
    "seniority",
    "salary_min",
    "salary_max",
    "currency",
    "posted_date",
    "match_score",
    "similarity",
    "skill_match",
    "skills",
    "technologies",
    "source",
    "ats_type",
    "apply_url",
    "career_url",
)


def job_to_row(job: Job) -> dict[str, Any]:
    match = job.match
    salary = job.salary
    return {
        "company": job.company_name,
        "canonical_company": job.canonical_company_name or job.company_name,
        "role": job.role,
        "normalized_role": job.normalized_role or job.role,
        "location": job.location.city or job.location.country or (
            "Remote" if job.location.is_remote else ""
        ),
        "work_mode": str(job.work_mode),
        "country": job.country or "",
        "employment_type": str(job.employment_type),
        "experience_min_years": job.experience.min_years,
        "experience_max_years": job.experience.max_years,
        "seniority": str(job.seniority),
        "salary_min": salary.min_amount if salary else None,
        "salary_max": salary.max_amount if salary else None,
        "currency": salary.currency if salary else None,
        "posted_date": job.posted_date.isoformat() if job.posted_date else "",
        "match_score": match.score if match else None,
        "similarity": match.similarity if match else None,
        "skill_match": match.skill if match else None,
        "skills": "; ".join(job.skills),
        "technologies": "; ".join(job.technologies),
        "source": job.source,
        "ats_type": str(job.ats_type),
        "apply_url": job.url,
        "career_url": job.career_url or "",
    }
