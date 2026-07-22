"""Source registry: loading, O(1) lookup, priority, stats."""

from __future__ import annotations

import json
from pathlib import Path

from app.models.enums import LegalMode, SourceType
from app.registry.loaders import JsonSourceLoader, YamlSourceLoader, loader_for_path
from app.registry.service import SourceRegistry

REPO_YAML = Path("data/ats_sources.yaml")


async def test_load_default_yaml_has_all_sources() -> None:
    registry = SourceRegistry()
    count = await registry.load_from(YamlSourceLoader(REPO_YAML))
    assert count == 24
    assert len(registry) == 24

    # O(1) lookup
    gh = registry.get("greenhouse")
    assert gh is not None and gh.priority == 2 and gh.source_type == SourceType.ATS

    # priority order: career_site first (1), linkedin last (24)
    ordered = registry.by_priority()
    assert ordered[0].name == "career_site"
    assert ordered[-1].name == "linkedin"


async def test_enabled_and_stats() -> None:
    registry = SourceRegistry()
    await registry.load_from(YamlSourceLoader(REPO_YAML))

    enabled = registry.enabled()
    assert all(s.enabled for s in enabled)
    assert "linkedin" not in {s.name for s in enabled}  # disabled

    stats = registry.stats()
    assert stats.total == 24
    assert stats.enabled + stats.disabled == 24
    assert "linkedin" in stats.scrape_sources
    assert stats.by_source_type[str(SourceType.ATS)] == 15


async def test_json_loader_and_override(tmp_path: Path) -> None:
    registry = SourceRegistry()
    await registry.load_from(YamlSourceLoader(REPO_YAML))

    # A JSON overlay disables greenhouse — later load overrides earlier.
    override = tmp_path / "override.json"
    override.write_text(json.dumps([{"name": "greenhouse", "enabled": False, "priority": 2}]))
    await registry.load_from(loader_for_path(override))

    gh = registry.get("greenhouse")
    assert gh is not None and gh.enabled is False
    assert isinstance(loader_for_path(override), JsonSourceLoader)


async def test_linkedin_is_scrape_and_disabled() -> None:
    registry = SourceRegistry()
    await registry.load_from(YamlSourceLoader(REPO_YAML))
    li = registry.get("linkedin")
    assert li is not None and li.legal_mode == LegalMode.SCRAPE and li.enabled is False
