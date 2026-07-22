"""Company alias resolution."""

from __future__ import annotations

from pathlib import Path

from app.importers.aliases import AliasResolver
from app.models.company import Company

ALIAS_FILE = Path("data/company_aliases.yaml")


def test_resolve_known_alias() -> None:
    resolver = AliasResolver.from_file(ALIAS_FILE)
    assert len(resolver) > 0
    assert resolver.resolve("Google") == ("alphabet", "Alphabet")
    assert resolver.resolve("  facebook ") == ("meta", "Meta")  # case/space-insensitive


def test_apply_folds_company_onto_canonical() -> None:
    resolver = AliasResolver.from_file(ALIAS_FILE)
    company = Company(name="Walmart Global Tech", slug="walmart-global-tech")
    resolver.apply(company)
    assert company.canonical_slug == "walmart"
    assert "Walmart Global Tech" in company.aliases


def test_unknown_name_unchanged() -> None:
    resolver = AliasResolver.from_file(ALIAS_FILE)
    company = Company(name="Nobody Inc", slug="nobody")
    resolver.apply(company)
    assert company.canonical_slug is None


def test_missing_file_is_empty() -> None:
    resolver = AliasResolver.from_file(Path("does-not-exist.yaml"))
    assert len(resolver) == 0
    assert resolver.resolve("Google") is None
