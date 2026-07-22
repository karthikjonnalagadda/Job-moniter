"""User preferences + resume versioning.

Supports multiple named resume versions (v1, v2, Backend, AI, QA, Data, ...)
without schema redesign: each is a ``ResumeVersion`` with its own text and
embedding. The active version's embedding is also surfaced at the top level as
``resume_embedding`` (per the approved decision to store it in
``user_preferences``), which the ranking query uses directly.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.base import AppBaseModel, MongoDocument
from app.models.common import DEFAULT_USER_ID
from app.models.enums import WorkMode


class ResumeVersion(AppBaseModel):
    """One named resume variant and its embedding."""

    version_id: str  # stable key, e.g. "v1", "backend", "ai", "qa", "data"
    label: str  # human label, e.g. "Backend Resume"
    text: str | None = None  # raw resume text (or None if stored by path)
    source_path: str | None = None
    is_active: bool = False
    embedding: list[float] | None = None  # 384-dim embedding of this version
    created_at: datetime | None = None


class UserPreferences(MongoDocument):
    """Per-user matching preferences and resume library."""

    user_id: str = DEFAULT_USER_ID  # unique

    # Resume versioning.
    resume_versions: list[ResumeVersion] = Field(default_factory=list)
    active_resume_id: str | None = None
    resume_embedding: list[float] | None = None  # active version's embedding

    # Matching preferences.
    target_roles: list[str] = Field(default_factory=list)
    target_locations: list[str] = Field(default_factory=list)
    preferred_work_modes: list[WorkMode] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    min_score: int = 70
    max_experience_years: int = 2

    def active_resume(self) -> ResumeVersion | None:
        """Return the active resume version, if any."""

        for version in self.resume_versions:
            if version.version_id == self.active_resume_id:
                return version
        return None
