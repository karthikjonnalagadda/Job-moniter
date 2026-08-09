"""Controlled live verification of career URLs.

Given a career URL, this performs ONE polite HTTP GET (browser-like UA, bounded
timeout, capped body read, redirects followed but suspicious cross-domain hops
flagged) and classifies the result:

    working      2xx and the page looks like a careers/jobs page (or is an ATS)
    redirected   reached a careers/ATS page via a redirect chain
    unverified   reachable but not identifiable as careers, or a network hiccup
    blocked      explicitly refused (401/403/429/451) - often bot protection
    not_found    404/410
    invalid      the URL itself is malformed / non-http

It also scans the returned HTML for an ATS destination embedded behind a
corporate careers page (``company.com/careers`` -> ``company.wd1.myworkdayjobs.com``)
so the corporate URL is kept while the discovered ATS URL is recorded separately.

Pure-ish and dependency-light: it uses ``httpx`` (already a project dep) and the
existing ``ATSDetector``. No global state; concurrency/rate-limiting is applied
by the caller via ``verify_many``.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

import httpx

from app.importers.mnc_excel import normalize_url, registrable_domain
from app.routing.detector import ATSDetector
from app.routing.workday import parse_workday_url

# A realistic browser UA - this is a light liveness probe, not scraping; a bot UA
# trips corporate WAFs and yields false "blocked" verdicts.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

# Host fragments that identify an ATS destination (mirrors detector markers).
_ATS_HOST_MARKERS: tuple[str, ...] = (
    "myworkdayjobs.com", "myworkdaysite.com", "greenhouse.io", "lever.co",
    "ashbyhq.com", "smartrecruiters.com", "bamboohr.com", "teamtailor.com",
    "recruitee.com", "jobvite.com", "icims.com", "oraclecloud.com", "taleo.net",
    "sapsf.com", "sapsf.eu", "successfactors.com", "comeet.co", "breezy.hr",
    "applytojob.com", "workable.com", "phenompeople.com", "eightfold.ai",
    "avature.net", "ultipro.com", "dayforcehcm.com",
)
_ATS_URL_RE = re.compile(
    r"https?://[A-Za-z0-9.\-]+(?:"
    + "|".join(re.escape(m) for m in _ATS_HOST_MARKERS)
    + r")[^\s\"'<>]*",
    re.IGNORECASE,
)

# Signals that a page is genuinely about jobs/careers (checked in <title> + body head).
_CAREERS_SIGNALS = (
    "career", "careers", "jobs", "job openings", "vacanc", "apply now",
    "open positions", "open roles", "work with us", "join us", "join our team",
    "life at", "we're hiring", "we are hiring", "job search", "current openings",
    "explore opportunities", "search jobs",
)


@dataclass
class VerifyResult:
    company: str
    input_url: str
    final_url: str = ""
    http_status: int = 0
    redirect_url: str = ""          # first redirect hop, if any
    career_status: str = "unverified"
    is_careers_page: bool = False
    discovered_ats_url: str = ""
    ats_platform: str = ""          # detector value on final/discovered URL
    ats_token: str = ""             # board token, when the ATS URL encodes one
    ats_tenant: str = ""            # Workday tenant (first host label)
    ats_board: str = ""             # Workday site / board (first non-locale path seg)
    ats_confidence: float = 0.0
    suspicious_redirect: bool = False
    error: str = ""
    notes: list[str] = field(default_factory=list)


def _looks_like_careers(html_head: str, final_url: str) -> bool:
    hay = f"{final_url}\n{html_head}".lower()
    return any(sig in hay for sig in _CAREERS_SIGNALS)


def _find_embedded_ats(html: str, detector: ATSDetector) -> tuple[str, str, str, float]:
    """Return (ats_url, ats_value, token, confidence) for the first ATS link."""

    for match in _ATS_URL_RE.finditer(html):
        url = normalize_url(match.group(0))
        det = detector.detect(url)
        if det.detected:
            return url, det.ats_type.value, det.token or "", det.confidence
    return "", "", "", 0.0


class CareerUrlVerifier:
    def __init__(self, detector: ATSDetector | None = None) -> None:
        self._detector = detector or ATSDetector()

    async def verify(self, client: httpx.AsyncClient, company: str, url: str) -> VerifyResult:
        res = VerifyResult(company=company, input_url=url)
        norm = normalize_url(url)
        if not norm:
            res.career_status = "invalid"
            res.error = "malformed or non-http URL"
            return res

        try:
            resp = await client.get(norm)
        except httpx.TooManyRedirects:
            res.career_status = "unverified"
            res.error = "too many redirects"
            return res
        except (httpx.ConnectError, httpx.ConnectTimeout):
            res.career_status = "unverified"
            res.error = "connection failed"
            return res
        except httpx.ReadTimeout:
            res.career_status = "unverified"
            res.error = "read timeout"
            return res
        except httpx.HTTPError as exc:
            res.career_status = "unverified"
            res.error = f"{type(exc).__name__}: {str(exc)[:80]}"
            return res

        res.http_status = resp.status_code
        res.final_url = normalize_url(str(resp.url))
        if resp.history:
            first_hop = resp.history[0].headers.get("location", res.final_url)
            res.redirect_url = normalize_url(str(first_hop))

        # Cross-domain redirect safety check.
        origin = registrable_domain(norm)
        final_dom = registrable_domain(res.final_url)
        redirected = bool(resp.history) and final_dom != origin
        if (
            redirected
            and final_dom not in _ATS_HOST_MARKERS
            and not _shares_token(company, final_dom)
        ):
            res.suspicious_redirect = True
            res.notes.append(f"redirect left origin '{origin}' -> '{final_dom}'")

        # Body (bounded) for careers signal + embedded ATS discovery.
        html = ""
        ctype = resp.headers.get("content-type", "")
        if "html" in ctype or "text" in ctype:
            html = resp.text[:200_000]

        # ATS detection: final URL first, then embedded links.
        det = self._detector.detect(res.final_url)
        if det.detected:
            res.ats_platform, res.ats_confidence = det.ats_type.value, det.confidence
            res.ats_token = det.token or ""
            res.discovered_ats_url = res.final_url
        elif html:
            ats_url, ats_val, tok, conf = _find_embedded_ats(html, self._detector)
            if ats_url:
                res.discovered_ats_url, res.ats_platform = ats_url, ats_val
                res.ats_token, res.ats_confidence = tok, conf
                res.notes.append(f"embedded ATS: {ats_val}")

        # Workday carries its tenant+site in the URL structure (not a flat token);
        # extract them so the CXS collector can be driven from stored data.
        if res.ats_platform == "workday":
            coords = parse_workday_url(res.discovered_ats_url)
            if coords is not None:
                res.ats_tenant, res.ats_board = coords.tenant, coords.site

        res.is_careers_page = bool(res.ats_platform) or _looks_like_careers(
            html[:8000], res.final_url
        )

        # ---- Classify ----
        code = resp.status_code
        if code in (401, 403, 429, 451):
            res.career_status = "blocked"
        elif code in (404, 410):
            res.career_status = "not_found"
        elif 200 <= code < 300:
            if res.suspicious_redirect:
                res.career_status = "unverified"
            elif res.is_careers_page:
                res.career_status = "redirected" if resp.history else "working"
            else:
                res.career_status = "unverified"
                res.notes.append("2xx but no careers signal")
        elif 300 <= code < 400:
            res.career_status = "redirected"
        else:
            res.career_status = "unverified"
        return res


def _shares_token(company: str, domain: str) -> bool:
    """True if the company name and a redirect domain share a meaningful token
    (so ``Mercedes-Benz`` -> ``group.mercedes-benz.com`` is not 'suspicious')."""

    dom_core = domain.split(".")[0].lower()
    tokens = re.findall(r"[a-z0-9]+", company.lower())
    return any(len(t) >= 4 and (t in dom_core or dom_core in t) for t in tokens)


async def verify_many(
    items: list[tuple[str, str]],
    *,
    concurrency: int = 8,
    timeout_s: float = 12.0,
    per_request_delay: float = 0.15,
) -> list[VerifyResult]:
    """Verify ``(company, url)`` pairs with bounded concurrency and politeness."""

    verifier = CareerUrlVerifier()
    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    timeout_cfg = httpx.Timeout(timeout_s, connect=timeout_s)

    async with httpx.AsyncClient(
        follow_redirects=True,
        max_redirects=5,
        timeout=timeout_cfg,
        limits=limits,
        headers={"User-Agent": _BROWSER_UA, "Accept": "text/html,*/*"},
        verify=True,
    ) as client:

        async def _one(company: str, url: str) -> VerifyResult:
            async with sem:
                result = await verifier.verify(client, company, url)
                await asyncio.sleep(per_request_delay)  # be polite
                return result

        return await asyncio.gather(*(_one(c, u) for c, u in items))
