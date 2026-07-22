"""Parser shapes, loader error paths, and validation edge cases."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.exceptions import ConfigurationError, ValidationError
from app.importers.parsers import detect_format, parse_records
from app.importers.validation import CompanyValidator
from app.registry.loaders import (
    JsonSourceLoader,
    YamlSourceLoader,
    loader_for_path,
)
from app.registry.service import SourceRegistry


# ---- parsers ----------------------------------------------------------------
def test_parse_json_list_shape(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    path.write_text('[{"company":"A","slug":"a"}]')
    records = list(parse_records(path))
    assert records == [(1, {"company": "A", "slug": "a"})]


def test_parse_json_slug_mapping_shape(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    path.write_text('{"a": {"company": "A"}}')
    (_, record) = next(iter(parse_records(path)))
    assert record["slug"] == "a" and record["company"] == "A"


def test_parse_yaml_companies_key(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("companies:\n  - company: A\n    slug: a\n")
    assert list(parse_records(path)) == [(1, {"company": "A", "slug": "a"})]


def test_parse_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "c.txt"
    path.write_text("x")
    with pytest.raises(ValidationError):
        list(parse_records(path))


def test_parse_missing_file() -> None:
    with pytest.raises(ValidationError):
        list(parse_records(Path("does-not-exist.csv")))


def test_detect_format() -> None:
    assert detect_format(Path("a.csv")) == "csv"
    assert detect_format(Path("a.yml")) == "yaml"
    assert detect_format(Path("a.txt")) == "unknown"


# ---- loaders ----------------------------------------------------------------
async def test_yaml_loader_missing_file() -> None:
    with pytest.raises(ConfigurationError):
        await YamlSourceLoader(Path("nope.yaml")).load()


async def test_yaml_loader_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "s.yaml"
    path.write_text("- just\n- a\n- list\n")
    with pytest.raises(ConfigurationError):
        await YamlSourceLoader(path).load()


async def test_json_loader_list_and_bad_shape(tmp_path: Path) -> None:
    good = tmp_path / "s.json"
    good.write_text('[{"name": "greenhouse", "priority": 2}]')
    defs = await JsonSourceLoader(good).load()
    assert defs[0].name == "greenhouse"

    bad = tmp_path / "bad.json"
    bad.write_text("42")
    with pytest.raises(ConfigurationError):
        await JsonSourceLoader(bad).load()


def test_loader_for_path_unsupported() -> None:
    with pytest.raises(ConfigurationError):
        loader_for_path(Path("x.txt"))


async def test_registry_by_source_type() -> None:
    from app.registry.loaders import YamlSourceLoader as YL

    registry = SourceRegistry()
    await registry.load_from(YL(Path("data/ats_sources.yaml")))
    from app.models.enums import SourceType

    ats = registry.by_source_type(SourceType.ATS)
    assert len(ats) == 15


# ---- validation edge cases --------------------------------------------------
def test_unparseable_bool_is_dropped() -> None:
    valid, report = CompanyValidator().validate(
        [(1, {"company": "A", "slug": "a", "active": "maybe"})]
    )
    assert report.is_valid  # unparseable bool dropped, row still valid
    assert valid[0][1].active_status is True  # falls back to model default
