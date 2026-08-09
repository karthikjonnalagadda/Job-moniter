"""Deterministic tests for Workday tenant/site extraction (no network).

Covers the coordinate extraction the CXS collector needs (host/tenant/site),
the data-center label variants (wd1/wd3/wd5/wd501), locale stripping, and the
false-positive guard: a corporate ``workday.com`` page or any unrelated
"workday" string must never yield coordinates.
"""

from __future__ import annotations

import pytest
from app.routing.workday import (
    WorkdayCoords,
    is_workday_url,
    parse_workday_url,
)


@pytest.mark.parametrize(
    ("url", "tenant", "site"),
    [
        # Plain data-center variants; site is the first path segment.
        ("https://acme.wd1.myworkdayjobs.com/External", "acme", "External"),
        ("https://acme.wd3.myworkdayjobs.com/careers", "acme", "careers"),
        ("https://aig.wd1.myworkdayjobs.com/aig", "aig", "aig"),
        # Locale segment is skipped; the real site follows it.
        ("https://airproducts.wd5.myworkdayjobs.com/en-US/AP0001", "airproducts", "AP0001"),
        ("https://bristolmyerssquibb.wd5.myworkdayjobs.com/en-US/BMS/login",
         "bristolmyerssquibb", "BMS"),
        # Deep links: only the site segment is kept.
        ("https://bdx.wd1.myworkdayjobs.com/EXTERNAL_CAREER_SITE_USA/login",
         "bdx", "EXTERNAL_CAREER_SITE_USA"),
        ("https://gevernova.wd5.myworkdayjobs.com/Vernova_ExternalSite/job/Allentown/x",
         "gevernova", "Vernova_ExternalSite"),
        # Multi-digit data-center label.
        ("https://forrester.wd501.myworkdayjobs.com/careers", "forrester", "careers"),
        # The user-supplied normalisation example.
        ("https://workday.wd5.myworkdayjobs.com/Workday/?source=Careers_Website",
         "workday", "Workday"),
        # No wd{N} label at all.
        ("https://acme.myworkdayjobs.com/External", "acme", "External"),
        # The myworkdaysite.com tenant-in-host variant.
        ("https://acme.wd3.myworkdaysite.com/CareerSite", "acme", "CareerSite"),
        # Bare host (no scheme) still parses.
        ("acme.wd1.myworkdayjobs.com/External", "acme", "External"),
    ],
)
def test_parse_extracts_tenant_and_site(url: str, tenant: str, site: str) -> None:
    coords = parse_workday_url(url)
    assert coords is not None
    assert coords.tenant == tenant
    assert coords.site == site
    assert coords.host.endswith("myworkdayjobs.com") or coords.host.endswith("myworkdaysite.com")


@pytest.mark.parametrize(
    ("url", "host", "tenant", "site"),
    [
        # Form B: the data-center host carries tenant + site in the path.
        ("https://wd3.myworkdaysite.com/recruiting/riotinto/RioTinto_Careers/login",
         "wd3.myworkdaysite.com", "riotinto", "RioTinto_Careers"),
        ("https://wd5.myworkdaysite.com/recruiting/acmeco/External",
         "wd5.myworkdaysite.com", "acmeco", "External"),
    ],
)
def test_parse_recruiting_path_form(url: str, host: str, tenant: str, site: str) -> None:
    coords = parse_workday_url(url)
    assert coords is not None
    # host is the data-center; the CXS endpoint is built as {host}/wday/cxs/{tenant}/{site}
    assert coords.to_extra() == {"host": host, "tenant": tenant, "site": site}


def test_to_extra_matches_collector_contract() -> None:
    coords = parse_workday_url("https://acme.wd1.myworkdayjobs.com/en-US/External")
    assert coords is not None
    assert coords.to_extra() == {
        "host": "acme.wd1.myworkdayjobs.com",
        "tenant": "acme",
        "site": "External",
    }


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "not-a-url",
        "https://workday.com/careers",              # corporate marketing site
        "https://careers.workday.com/en-US/jobs",    # Workday's OWN careers site
        "https://myworkday.example.com/careers",     # unrelated host containing 'workday'
        "https://acme.myworkdayjobs.com.evil.com/x",  # suffix-spoof
        "https://greenhouse.io/acme",                # a different ATS
        "https://acme.wd1.myworkdayjobs.com",        # no site path segment
        "https://acme.wd1.myworkdayjobs.com/en-US",  # only a locale, no site
        "https://wd3.myworkdaysite.com/recruiting/onlytenant",  # recruiting path too short
        "https://wd3.myworkdaysite.com/careers",     # data-center host, no recruiting path
    ],
)
def test_non_workday_or_incomplete_returns_none(url: str | None) -> None:
    assert parse_workday_url(url) is None


def test_is_workday_url_guard() -> None:
    assert is_workday_url("https://acme.wd1.myworkdayjobs.com/External") is True
    assert is_workday_url("https://acme.wd1.myworkdayjobs.com") is True  # host only
    assert is_workday_url("https://workday.com/careers") is False
    assert is_workday_url("https://careers.workday.com/en-US") is False
    assert is_workday_url(None) is False


def test_coords_are_frozen() -> None:
    from dataclasses import FrozenInstanceError

    coords = WorkdayCoords(host="acme.wd1.myworkdayjobs.com", tenant="acme", site="External")
    with pytest.raises(FrozenInstanceError):
        coords.tenant = "other"  # type: ignore[misc]
