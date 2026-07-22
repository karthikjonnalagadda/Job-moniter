"""Role normalization — map a job title to a canonical role from the taxonomy.

E.g. "Sr. Machine Learning Engineer (NLP)" → "ML Engineer". Falls back to a
title-cased cleanup of the original when no taxonomy entry matches, so the
``normalized_role`` field is always populated.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.normalization.taxonomy import SynonymIndex, load_yaml

_DEFAULT_ROLES: dict[str, list[str]] = {
    "ML Engineer": ["machine learning engineer", "ml engineer", "ai engineer"],
    "Backend Engineer": ["backend engineer", "backend developer", "back-end engineer"],
    "Frontend Engineer": ["frontend engineer", "frontend developer", "front-end engineer"],
    "Data Engineer": ["data engineer"],
    "Data Scientist": ["data scientist"],
    "DevOps Engineer": ["devops engineer", "devops", "sre", "site reliability engineer"],
    "QA Engineer": ["qa engineer", "quality assurance", "sdet", "test engineer"],
}
_NOISE = re.compile(r"\b(sr|senior|jr|junior|lead|staff|principal|intern|i{1,3}|iv|v)\b", re.I)


class RoleNormalizer:
    """Normalise a raw job title to a canonical role."""

    def __init__(self, index: SynonymIndex) -> None:
        self._index = index

    @classmethod
    def from_file(cls, path: Path | None) -> RoleNormalizer:
        data = load_yaml(path)
        mapping = data if isinstance(data, dict) else _DEFAULT_ROLES
        return cls(SynonymIndex(mapping))

    def normalize(self, title: str | None) -> str | None:
        if not title or not str(title).strip():
            return None
        text = str(title).strip()
        match = self._index.find_first(text)
        if match is not None:
            return match
        return self._fallback(text)

    @staticmethod
    def _fallback(title: str) -> str:
        # Strip seniority/parenthetical noise, collapse whitespace, title-case.
        cleaned = re.sub(r"\(.*?\)", " ", title)
        cleaned = _NOISE.sub(" ", cleaned)
        cleaned = re.sub(r"[^A-Za-z0-9/ +.-]", " ", cleaned)
        cleaned = " ".join(cleaned.split())
        return cleaned.title() if cleaned else title.strip()
