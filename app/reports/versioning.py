"""Report versioning — stamps every report with the versions that produced it.

* ``report_version``    — the report schema/layout version (this module);
* ``schema_version``    — the normalised Job schema version;
* ``pipeline_version``  — the application/pipeline version;
* ``collector_versions``— versions of the collectors that produced the jobs.
"""

from __future__ import annotations

from pydantic import Field

from app import __version__ as PIPELINE_VERSION
from app.models.base import AppBaseModel
from app.models.common import JOB_SCHEMA_VERSION

REPORT_VERSION = 1


class ReportVersions(AppBaseModel):
    report_version: int = REPORT_VERSION
    schema_version: int = JOB_SCHEMA_VERSION
    pipeline_version: str = PIPELINE_VERSION
    collector_versions: dict[str, str] = Field(default_factory=dict)


def build_versions(collector_versions: dict[str, str] | None = None) -> ReportVersions:
    return ReportVersions(collector_versions=collector_versions or {})
