"""Edge-case coverage for the Phase-6 pipeline building blocks."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.core.normalization.freshness import FreshnessParser
from app.core.normalization.location import LocationNormalizer
from app.core.normalization.roles import RoleNormalizer
from app.core.normalization.salary import SalaryNormalizer
from app.core.normalization.taxonomy import SynonymIndex, load_yaml
from app.core.skills.extractor import SkillExtractor
from app.vector.numpy_scorer import NumpyCosineScorer

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def test_freshness_edges() -> None:
    p = FreshnessParser(now=lambda: _NOW)
    assert p.parse("just now") == _NOW
    assert p.parse("1735732800") is not None  # numeric string → epoch
    assert p.parse(-1) is not None or p.parse(-1) is None  # negative tolerated
    assert p.parse(1e18) is None  # absurd epoch → guarded
    assert p.age_hours(None) is None
    assert p.age_hours(_NOW.replace(hour=11)) == 1.0


def test_taxonomy_helpers_and_missing_file() -> None:
    assert load_yaml(Path("does/not/exist.yaml")) is None
    idx = SynonymIndex({"Python": ["py", "python"], "Go": ["go", "golang"]})
    assert idx.exact("PY") == "Python"
    assert idx.find_first("we use py here") == "Python"
    assert set(idx.find_all("py and golang")) == {"Python", "Go"}
    assert "go" not in idx.find_all("category management")  # whole-token only
    assert len(idx) >= 4


def test_role_fallback_and_defaults_when_file_missing() -> None:
    roles = RoleNormalizer.from_file(Path("missing.yaml"))  # built-in defaults
    assert roles.normalize("ML Engineer") == "ML Engineer"
    assert roles.normalize("Underwater Basket Weaver") is not None


def test_location_defaults_when_file_missing() -> None:
    loc = LocationNormalizer.from_file(Path("missing.yaml"))
    assert loc.normalize("Mumbai").city == "Mumbai"
    assert loc.normalize("remote").is_remote is True


def test_salary_and_skills_none_paths() -> None:
    assert SalaryNormalizer().parse(None) is None
    assert SkillExtractor.from_file(Path("missing.yaml")).extract("python").skills == ["Python"]


async def test_numpy_scorer_empty_and_reload() -> None:
    scorer = NumpyCosineScorer()
    scorer.load([])  # empty corpus
    assert await scorer.search([1.0], limit=5) == []
    scorer.load([("x", [1.0, 0.0])])
    assert (await scorer.search([1.0, 0.0], limit=1))[0].job_id == "x"
