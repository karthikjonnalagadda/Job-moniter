"""Company validation engine.

Normalises raw import records (column aliasing, type coercion) and validates
them both per-row (required fields, malformed URLs, invalid ATS type,
unsupported country) and cross-row (duplicate slug / career URL / ATS token).
Produces a ``ValidationReport`` and the list of rows that are safe to import.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError as PydanticValidationError

from app.importers.models import ValidationIssue, ValidationReport, ValidationSeverity
from app.models.company import Company
from app.models.enums import ATSType, CompanyCategory, CrawlFrequency, HiringCategory

# Map common column names to canonical Company field names.
_FIELD_ALIASES: dict[str, str] = {
    "company": "name",
    "name": "name",
    "company_name": "name",
    "slug": "slug",
    "career_url": "career_url",
    "careerurl": "career_url",
    "career_page": "career_url",
    "careers": "career_url",
    "url": "career_url",
    "career_platform": "career_platform",
    "platform": "career_platform",
    "ats": "ats_type",
    "ats_type": "ats_type",
    "ats_platform": "ats_type",
    "ats_token": "ats_token",
    "board_token": "ats_token",
    "token": "ats_token",
    "industry": "industry",
    "headquarters": "headquarters",
    "hq": "headquarters",
    "country": "country",
    "company_category": "company_category",
    "category": "company_category",
    "hiring_category": "hiring_category",
    "priority_score": "priority_score",
    "priority": "priority_score",
    "ai_hiring_score": "ai_hiring_score",
    "remote_support": "remote_support",
    "remote": "remote_support",
    "active_status": "active_status",
    "active": "active_status",
    "crawl_frequency": "crawl_frequency",
    "frequency": "crawl_frequency",
    "supported_roles": "supported_roles",
    "roles": "supported_roles",
    "preferred_technologies": "preferred_technologies",
    "technologies": "preferred_technologies",
    "tech_stack": "preferred_technologies",
    "aliases": "aliases",
    "notes": "notes",
}

_TRUE = {"true", "1", "yes", "y", "t", "on"}
_FALSE = {"false", "0", "no", "n", "f", "off"}

# Fields that are lists on the model; CSV supplies them as delimited strings.
_LIST_FIELDS = ("supported_roles", "preferred_technologies", "aliases")
_LIST_DELIMITERS = (";", "|")

_ATS_VALUES = {a.value for a in ATSType}
_HIRING_CATEGORY_VALUES = {c.value for c in HiringCategory}
_COMPANY_CATEGORY_VALUES = {c.value for c in CompanyCategory}
_CRAWL_FREQUENCY_VALUES = {c.value for c in CrawlFrequency}


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def _split_list(value: Any) -> list[str]:
    """Coerce a delimited string (or existing list) into a clean list of strings."""

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value)
    for delimiter in _LIST_DELIMITERS:
        if delimiter in text:
            return [part.strip() for part in text.split(delimiter) if part.strip()]
    return [text.strip()] if text.strip() else []


def normalize_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Map aliased/whitespaced columns to canonical Company fields."""

    out: dict[str, Any] = {}
    for key, value in raw.items():
        canonical = _FIELD_ALIASES.get(str(key).strip().lower().replace(" ", "_"))
        if canonical is None:
            continue
        if canonical in _LIST_FIELDS:
            coerced = _split_list(value)
            if coerced:
                out[canonical] = coerced
            continue
        if isinstance(value, str):
            value = value.strip()
        if value in ("", None):
            continue
        out[canonical] = value
    return out


def _issue(
    code: str,
    message: str,
    *,
    row: int,
    slug: str | None,
    field: str | None = None,
    severity: ValidationSeverity = ValidationSeverity.ERROR,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        message=message,
        severity=severity,
        row=row,
        slug=slug,
        field=field,
    )


class CompanyValidator:
    """Validates and normalises company import records."""

    def __init__(self, *, allowed_countries: frozenset[str] | None = None) -> None:
        # If provided, country codes/names outside this set are rejected.
        self._allowed_countries = allowed_countries

    def validate(
        self, records: Iterable[tuple[int, dict[str, Any]]]
    ) -> tuple[list[tuple[int, Company]], ValidationReport]:
        valid: list[tuple[int, Company]] = []
        issues: list[ValidationIssue] = []
        seen_slug: set[str] = set()
        seen_url: set[str] = set()
        seen_token: set[str] = set()
        total = 0
        invalid = 0

        for row, raw in records:
            total += 1
            norm = normalize_raw(raw)
            row_issues = self._check_row(row, norm)
            self._check_duplicates(row, norm, row_issues, seen_slug, seen_url, seen_token)

            company = self._build(row, norm, row_issues)
            issues.extend(row_issues)
            has_error = any(i.severity == ValidationSeverity.ERROR for i in row_issues)
            if company is not None and not has_error:
                valid.append((row, company))
            else:
                invalid += 1

        report = ValidationReport(
            total_rows=total,
            valid_rows=len(valid),
            invalid_rows=invalid,
            issues=issues,
        )
        return valid, report

    # ---- per-row checks -------------------------------------------------
    def _check_row(self, row: int, norm: dict[str, Any]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        slug = norm.get("slug")

        for field in ("name", "slug"):
            if not norm.get(field):
                issues.append(
                    _issue(
                        "missing_required_field",
                        f"Missing required field '{field}'",
                        row=row,
                        slug=slug,
                        field=field,
                    )
                )

        url = norm.get("career_url")
        if url and not self._is_valid_url(str(url)):
            issues.append(
                _issue(
                    "malformed_url",
                    f"Malformed URL '{url}'",
                    row=row,
                    slug=slug,
                    field="career_url",
                )
            )

        ats = norm.get("ats_type")
        if ats is not None:
            if str(ats).lower() not in _ATS_VALUES:
                issues.append(
                    _issue(
                        "invalid_ats_type",
                        f"Unknown ATS type '{ats}'",
                        row=row,
                        slug=slug,
                        field="ats_type",
                    )
                )
            else:
                norm["ats_type"] = str(ats).lower()

        category = norm.get("hiring_category")
        if category is not None and str(category).lower() not in _HIRING_CATEGORY_VALUES:
            issues.append(
                _issue(
                    "invalid_hiring_category",
                    f"Unknown hiring category '{category}' (defaulting to unknown)",
                    row=row,
                    slug=slug,
                    field="hiring_category",
                    severity=ValidationSeverity.WARNING,
                )
            )
            norm.pop("hiring_category", None)

        company_category = norm.get("company_category")
        if (
            company_category is not None
            and str(company_category).lower() not in _COMPANY_CATEGORY_VALUES
        ):
            issues.append(
                _issue(
                    "invalid_company_category",
                    f"Unknown company category '{company_category}' (defaulting to unknown)",
                    row=row,
                    slug=slug,
                    field="company_category",
                    severity=ValidationSeverity.WARNING,
                )
            )
            norm.pop("company_category", None)
        elif company_category is not None:
            norm["company_category"] = str(company_category).lower()

        frequency = norm.get("crawl_frequency")
        if frequency is not None and str(frequency).lower() not in _CRAWL_FREQUENCY_VALUES:
            issues.append(
                _issue(
                    "invalid_crawl_frequency",
                    f"Unknown crawl frequency '{frequency}' (defaulting to weekly)",
                    row=row,
                    slug=slug,
                    field="crawl_frequency",
                    severity=ValidationSeverity.WARNING,
                )
            )
            norm.pop("crawl_frequency", None)
        elif frequency is not None:
            norm["crawl_frequency"] = str(frequency).lower()

        country = norm.get("country")
        if (
            self._allowed_countries is not None
            and country
            and str(country).upper() not in self._allowed_countries
        ):
            issues.append(
                _issue(
                    "unsupported_country",
                    f"Unsupported country '{country}'",
                    row=row,
                    slug=slug,
                    field="country",
                )
            )

        self._coerce_booleans(norm)
        return issues

    def _check_duplicates(
        self,
        row: int,
        norm: dict[str, Any],
        row_issues: list[ValidationIssue],
        seen_slug: set[str],
        seen_url: set[str],
        seen_token: set[str],
    ) -> None:
        slug = norm.get("slug")
        for value, seen, code, field, label in (
            (slug, seen_slug, "duplicate_slug", "slug", "slug"),
            (norm.get("career_url"), seen_url, "duplicate_career_url", "career_url", "career URL"),
            (norm.get("ats_token"), seen_token, "duplicate_board_token", "ats_token", "ATS token"),
        ):
            if not value:
                continue
            if value in seen:
                row_issues.append(
                    _issue(code, f"Duplicate {label} '{value}'", row=row, slug=slug, field=field)
                )
            seen.add(value)

    @staticmethod
    def _coerce_booleans(norm: dict[str, Any]) -> None:
        for field in ("remote_support", "active_status"):
            if field in norm:
                coerced = _coerce_bool(norm[field])
                if coerced is None:
                    norm.pop(field)
                else:
                    norm[field] = coerced

    def _build(
        self, row: int, norm: dict[str, Any], row_issues: list[ValidationIssue]
    ) -> Company | None:
        if any(i.severity == ValidationSeverity.ERROR for i in row_issues):
            return None
        try:
            return Company.model_validate(norm)
        except PydanticValidationError as exc:
            message = str(exc.errors()[0].get("msg", exc))
            row_issues.append(_issue("schema_error", message, row=row, slug=norm.get("slug")))
            return None

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
