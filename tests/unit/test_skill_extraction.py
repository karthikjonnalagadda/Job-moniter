"""Skill extraction engine."""

from __future__ import annotations

from pathlib import Path

from app.core.skills.extractor import SkillExtractor

_EXTRACTOR = SkillExtractor.from_file(Path("data/taxonomies/skills.yaml"))


def test_extracts_categorised_skills() -> None:
    result = _EXTRACTOR.extract(
        "Build RAG pipelines with Python and FastAPI on AWS using Docker and PyTorch."
    )
    assert "Python" in result.skills
    assert "FastAPI" in result.skills
    assert "AWS" in result.skills
    assert "Docker" in result.skills
    # technologies excludes soft-skills/certs/degrees but includes these
    assert "Python" in result.technologies
    assert "languages" in result.by_category
    assert "cloud" in result.by_category


def test_whole_token_matching_avoids_false_positives() -> None:
    # "go" must not match inside "category"; "c" must not match every word.
    result = _EXTRACTOR.extract("We work in the category of data processing.")
    assert "Go" not in result.skills


def test_degrees_excluded_from_skills_but_present_in_categories() -> None:
    result = _EXTRACTOR.extract("Requires a B.Tech and strong communication skills.")
    assert "degrees" in result.by_category
    # degrees are not counted as skills, soft skills are
    assert all(s not in result.skills for s in result.by_category.get("degrees", []))


def test_empty_text() -> None:
    assert _EXTRACTOR.extract("").skills == []
    assert _EXTRACTOR.extract(None).skills == []
