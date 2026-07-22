"""Indian company seed: markdown parser + dataset builder + exporters."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from app.importers.india_seed import FIELD_ORDER, IndiaSeedBuilder
from app.importers.markdown_seed import parse_seed_table
from app.importers.validation import CompanyValidator

_SEED = Path("data/companies/Indian_Company_Career_Sites.csv")


def test_parse_seed_table_extracts_pairs() -> None:
    entries = parse_seed_table(_SEED)
    assert len(entries) >= 70
    names = {e.name for e in entries}
    assert "TCS" in names
    assert "Infosys" in names
    for entry in entries:
        assert entry.career_url.startswith("http")


def test_builder_from_seed_only_is_valid() -> None:
    builder = IndiaSeedBuilder()
    records = builder.build(_SEED, None)
    assert len(records) >= 70
    # every record carries the full canonical field set
    for field in FIELD_ORDER:
        assert field in records[0]
    # and imports cleanly through the real validator
    rows = [
        (i, {k: v for k, v in r.items() if not k.startswith("_")})
        for i, r in enumerate(records, 1)
    ]
    _, report = CompanyValidator().validate(rows)
    assert report.invalid_rows == 0


def test_builder_detects_ats_and_merges_metadata(tmp_path: Path) -> None:
    metadata = [
        {
            "name": "DemoCo",
            "slug": "democo",
            "career_url": "https://jobs.lever.co/democo",
            "industry": "SaaS",
            "company_category": "saas",
            "headquarters": "Bengaluru",
            "priority_score": 88,
            "supported_roles": ["Backend Engineer"],
        }
    ]
    meta_path = tmp_path / "meta.yaml"
    meta_path.write_text(yaml.safe_dump(metadata), encoding="utf-8")

    builder = IndiaSeedBuilder()
    records = builder.build(_SEED, meta_path)
    demo = next(r for r in records if r["slug"] == "democo")
    assert demo["ats_type"] == "lever"  # auto-detected from the Lever URL
    assert demo["ats_token"] == "democo"
    assert demo["career_platform"] == "Lever"
    assert demo["company_category"] == "saas"

    stats = builder.stats(records)
    assert stats.total == len(records)
    assert stats.ats_detected >= 1
    assert stats.by_category.get("saas", 0) >= 1


def test_write_outputs_roundtrips(tmp_path: Path) -> None:
    builder = IndiaSeedBuilder()
    records = builder.build(_SEED, None)
    paths = builder.write_outputs(records, tmp_path)
    assert paths["csv"].exists() and paths["json"].exists() and paths["yaml"].exists()

    loaded = json.loads(paths["json"].read_text(encoding="utf-8"))["companies"]
    assert len(loaded) == len(records)
    # provenance flags are stripped from exports
    assert "_from_seed" not in loaded[0]
    assert set(loaded[0].keys()) == set(FIELD_ORDER)
