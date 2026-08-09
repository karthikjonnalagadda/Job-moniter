"""URL verifier — hermetic tests (no network, via httpx.MockTransport).

Covers status classification, careers-page heuristic, embedded-ATS discovery +
token capture (ATS hidden behind a corporate careers page), suspicious-redirect
handling, and the offline token backfill.
"""

from __future__ import annotations

import httpx
import pytest
from app.importers.url_verifier import CareerUrlVerifier

from scripts.verify_mnc_urls import backfill_tokens


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        max_redirects=5,
    )


async def _verify(handler, url: str, company: str = "Acme"):
    async with _client(handler) as client:
        return await CareerUrlVerifier().verify(client, company, url)


async def test_working_careers_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html="<title>Careers at Acme</title> Open positions")

    res = await _verify(handler, "https://acme.com/careers")
    assert res.career_status == "working"
    assert res.http_status == 200
    assert res.is_careers_page is True


async def test_200_but_not_careers_is_unverified() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html="<title>Welcome</title> Buy our products")

    res = await _verify(handler, "https://acme.com/")
    assert res.career_status == "unverified"


async def test_not_found_and_blocked() -> None:
    nf = await _verify(lambda r: httpx.Response(404), "https://acme.com/x")
    bl = await _verify(lambda r: httpx.Response(403), "https://acme.com/x")
    assert nf.career_status == "not_found"
    assert bl.career_status == "blocked"


async def test_invalid_url() -> None:
    res = await _verify(lambda r: httpx.Response(200), "not-a-url")
    assert res.career_status == "invalid"


async def test_embedded_ats_discovered_with_token() -> None:
    # Corporate careers page that embeds a Greenhouse board link.
    def handler(request: httpx.Request) -> httpx.Response:
        html = (
            "<title>Careers</title>"
            '<a href="https://boards.greenhouse.io/acmecorp/jobs/123">See jobs</a>'
        )
        return httpx.Response(200, html=html)

    res = await _verify(handler, "https://acme.com/careers")
    assert res.career_status == "working"
    assert res.ats_platform == "greenhouse"
    assert res.ats_token == "acmecorp"
    assert res.discovered_ats_url.startswith("https://boards.greenhouse.io/acmecorp")
    # The official career URL is what we probed; discovery is stored separately.
    assert res.input_url == "https://acme.com/careers"


async def test_redirect_to_ats_is_redirected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "myworkdayjobs.com" in str(request.url):
            return httpx.Response(200, html="<title>Careers</title> jobs")
        return httpx.Response(301, headers={"location": "https://acme.wd1.myworkdayjobs.com/External"})

    res = await _verify(handler, "https://acme.com/careers")
    assert res.career_status == "redirected"
    assert res.ats_platform == "workday"
    # Workday tenant + site are extracted from the final board URL.
    assert res.ats_tenant == "acme"
    assert res.ats_board == "External"


async def test_embedded_workday_board_extracts_tenant_and_site() -> None:
    # Corporate careers page linking out to a Workday board (locale + site path).
    def handler(request: httpx.Request) -> httpx.Response:
        html = (
            "<title>Careers at Acme</title>"
            '<a href="https://acmecorp.wd5.myworkdayjobs.com/en-US/AcmeExternal/jobs">'
            "See openings</a>"
        )
        return httpx.Response(200, html=html)

    res = await _verify(handler, "https://acme.com/careers")
    assert res.ats_platform == "workday"
    assert res.ats_tenant == "acmecorp"
    assert res.ats_board == "AcmeExternal"
    assert res.discovered_ats_url.startswith("https://acmecorp.wd5.myworkdayjobs.com")
    # The official career URL is never replaced by discovery.
    assert res.input_url == "https://acme.com/careers"


async def test_suspicious_external_redirect_not_trusted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "spam-parking" in str(request.url):
            return httpx.Response(200, html="<title>Careers jobs</title>")
        return httpx.Response(302, headers={"location": "https://spam-parking-xyz.com/"})

    res = await _verify(handler, "https://acme.com/careers")
    assert res.suspicious_redirect is True
    assert res.career_status == "unverified"  # careers words present but redirect untrusted


def test_backfill_tokens_offline() -> None:
    master = [
        {"company_name": "Palantir", "ats_platform": "lever", "ats_token": "Unknown",
         "discovered_ats_url": "https://jobs.lever.co/palantir/abc"},
        {"company_name": "NoDiscovery", "ats_platform": "Unknown", "ats_token": "Unknown",
         "discovered_ats_url": ""},
        {"company_name": "AlreadySet", "ats_platform": "greenhouse", "ats_token": "known",
         "discovered_ats_url": "https://boards.greenhouse.io/other"},
    ]
    changed = backfill_tokens(master)
    assert changed == 1
    assert master[0]["ats_token"] == "palantir"
    assert master[2]["ats_token"] == "known"  # not overwritten


@pytest.mark.parametrize(
    ("code", "expected"),
    [(200, "unverified"), (410, "not_found"), (429, "blocked")],
)
async def test_status_matrix(code: int, expected: str) -> None:
    res = await _verify(lambda r: httpx.Response(code, html="nothing"), "https://acme.com/x")
    assert res.career_status == expected
