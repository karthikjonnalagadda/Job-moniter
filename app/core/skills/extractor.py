"""Skill extraction engine.

Extracts categorised skills from job/resume text using the ``skills.yaml``
taxonomy (canonical skill → synonyms, grouped by category). Synonyms are matched
on whole-token boundaries so ``go`` does not match ``category`` and ``c`` does
not match every word.

Categories: languages, frameworks, libraries, cloud, devops, databases, ai_ml,
testing, soft_skills, certifications, degrees. ``technologies`` is the union of
the technical categories (everything except soft_skills/certifications/degrees).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from app.core.normalization.taxonomy import SynonymIndex, load_yaml
from app.models.base import AppBaseModel

_TECH_CATEGORIES = frozenset(
    {"languages", "frameworks", "libraries", "cloud", "devops", "databases", "ai_ml", "testing"}
)
_NON_SKILL_CATEGORIES = frozenset({"certifications", "degrees"})

_DEFAULT_SKILLS: dict[str, dict[str, list[str]]] = {
    "languages": {"Python": ["python", "py"], "Java": ["java"], "Go": ["go", "golang"]},
    "frameworks": {"FastAPI": ["fastapi"], "React": ["react", "reactjs"]},
    "cloud": {"AWS": ["aws"], "Azure": ["azure"], "GCP": ["gcp", "google cloud"]},
    "devops": {"Docker": ["docker"], "Kubernetes": ["kubernetes", "k8s"]},
    "databases": {"MongoDB": ["mongodb", "mongo"], "PostgreSQL": ["postgresql", "postgres"]},
    "ai_ml": {"PyTorch": ["pytorch"], "RAG": ["rag", "retrieval augmented generation"]},
    "testing": {"Pytest": ["pytest"]},
    "soft_skills": {"Communication": ["communication"], "Leadership": ["leadership"]},
    "certifications": {},
    "degrees": {"B.Tech": ["b.tech", "btech"]},
}


class ExtractedSkills(AppBaseModel):
    """Categorised extraction result."""

    by_category: dict[str, list[str]] = Field(default_factory=dict)
    skills: list[str] = Field(default_factory=list)  # all canonical skills (flat)
    technologies: list[str] = Field(default_factory=list)  # technical subset

    @property
    def all_terms(self) -> set[str]:
        return set(self.skills)


class SkillExtractor:
    """Extract categorised skills from free text via the skills taxonomy."""

    def __init__(self, indices: dict[str, SynonymIndex]) -> None:
        self._indices = indices

    @classmethod
    def from_file(cls, path: Path | None) -> SkillExtractor:
        data = load_yaml(path)
        source = data if isinstance(data, dict) and data else _DEFAULT_SKILLS
        indices: dict[str, SynonymIndex] = {}
        for category, mapping in source.items():
            if isinstance(mapping, dict):
                indices[category] = SynonymIndex(
                    {str(k): [str(s) for s in (v or [])] for k, v in mapping.items()}
                )
        return cls(indices)

    def extract(self, *texts: str | None) -> ExtractedSkills:
        blob = " ".join(t for t in texts if t).lower()
        if not blob.strip():
            return ExtractedSkills()

        by_category: dict[str, list[str]] = {}
        skills: list[str] = []
        technologies: list[str] = []
        for category, index in self._indices.items():
            found = index.find_all(blob)
            if not found:
                continue
            by_category[category] = found
            if category not in _NON_SKILL_CATEGORIES:
                skills.extend(found)
            if category in _TECH_CATEGORIES:
                technologies.extend(found)

        return ExtractedSkills(
            by_category=by_category,
            skills=_dedupe(skills),
            technologies=_dedupe(technologies),
        )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
