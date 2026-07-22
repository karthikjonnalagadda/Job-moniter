"""Resume-version embeddings.

Each resume *version* (Backend / AI / QA / Data …) is embedded independently and
stored once, so rankings for different resumes stay independent. The stored
``content_hash`` lets the service skip regeneration when the resume text is
unchanged (embedding diff detection).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.base import MongoDocument
from app.models.common import DEFAULT_USER_ID, EMBEDDING_VERSION


class ResumeEmbedding(MongoDocument):
    """A stored embedding for one resume version."""

    resume_id: str  # stable id, e.g. "backend" / "ai" / "qa" / "data"
    label: str | None = None  # human-friendly name
    user_id: str = DEFAULT_USER_ID
    content_hash: str  # sha256 of the resume text (change detection)
    embedding: list[float] = Field(default_factory=list)
    dimensions: int = 0
    model_name: str = "hashing"
    model_version: str = "1"
    embedding_version: int = EMBEDDING_VERSION
    generated_at: datetime | None = None
    skills: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    max_experience_years: float = 2.0
