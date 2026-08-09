"""Workday tenant/site (board) extraction from a Workday careers URL.

A Workday job board lives on a per-customer host and needs three coordinates
before the CXS API can be called:

    https://{host}/wday/cxs/{tenant}/{site}/jobs

where ``host`` is ``{tenant}.wd{N}.myworkdayjobs.com`` (the data-center number N
varies per customer — wd1, wd3, wd5, wd103, wd501 …) and ``site`` is the first
non-locale path segment of the public careers URL. This module turns a
discovered Workday URL into those coordinates, deterministically and without any
network call, so the existing ``WorkdayCollector`` can be driven from stored
data:

    parse_workday_url("https://acme.wd1.myworkdayjobs.com/en-US/External/…")
      -> WorkdayCoords(host="acme.wd1.myworkdayjobs.com", tenant="acme",
                       site="External")

Only genuine Workday hosts match. ``workday.com`` (the corporate site) or any
unrelated string that merely contains the word "workday" never parses, so a
false ATS detection can never fabricate a tenant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

# Two public Workday URL shapes carry the tenant + site differently:
#
#   Form A  {tenant}.wd{N}.myworkdayjobs.com/[locale]/{site}/…
#           tenant is the first host label; site is the first non-locale path seg.
#           The wd{N} data-center label is optional; N is one or more digits.
#
#   Form B  wd{N}.myworkdaysite.com/recruiting/{tenant}/{site}/…
#           the host is just the data-center; tenant + site live in the path.
#
# Both resolve to the same CXS endpoint: https://{host}/wday/cxs/{tenant}/{site}/jobs
_WD_HOST_SUFFIXES: tuple[str, ...] = (".myworkdayjobs.com", ".myworkdaysite.com")
_WD_HOST_RE = re.compile(
    r"^(?P<tenant>[a-z0-9][a-z0-9-]*)\.(?:wd\d+\.)?myworkday(?:jobs|site)\.com$",
    re.IGNORECASE,
)
# A bare data-center label (wd3, wd501): valid as a host prefix, never a tenant.
_DATACENTER_RE = re.compile(r"^wd\d+$", re.IGNORECASE)
# A locale path segment such as en-US, fr-FR, zh-Hans (skipped before the site).
# Requires an explicit region so a real site named e.g. "hr" or "en" is never
# mistaken for a locale; Workday public URLs always use the hyphenated form.
_LOCALE_RE = re.compile(r"^[a-z]{2}-[a-z]{2,4}$", re.IGNORECASE)


def _workday_host(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.netloc.lower().split("@")[-1].split(":")[0]


@dataclass(frozen=True)
class WorkdayCoords:
    """The three coordinates the Workday CXS collector needs."""

    host: str
    tenant: str
    site: str

    def to_extra(self) -> dict[str, str]:
        """Render as the ``CollectorTarget.extra`` the Workday collector reads."""

        return {"host": self.host, "tenant": self.tenant, "site": self.site}


def _first_site_segment(path: str) -> str | None:
    """First path segment that is not a locale (site names are case-sensitive)."""

    for seg in path.split("/"):
        if not seg or _LOCALE_RE.match(seg):
            continue  # skip empty segments and a leading locale like en-US
        return seg
    return None


def parse_workday_url(url: str | None) -> WorkdayCoords | None:
    """Extract (host, tenant, site) from a Workday careers/board URL.

    Handles both public URL shapes (see module docstring). Returns ``None`` for
    any non-Workday host, a Workday host carrying no site, or a malformed URL —
    never a partial or guessed result.
    """

    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.lower().split("@")[-1].split(":")[0]
    if not any(host.endswith(suffix) for suffix in _WD_HOST_SUFFIXES):
        return None

    segments = [seg for seg in parsed.path.split("/") if seg]

    # Form B: wd{N}.myworkdaysite.com/recruiting/{tenant}/{site}/… — tenant + site
    # live in the path (the host is only the data-center).
    if len(segments) >= 3 and segments[0].lower() == "recruiting":
        return WorkdayCoords(host=host, tenant=segments[1], site=segments[2])

    # Form A: {tenant}.wd{N}.myworkdayjobs.com/[locale]/{site}/…
    match = _WD_HOST_RE.match(host)
    if not match:
        return None
    tenant = match.group("tenant")
    if _DATACENTER_RE.match(tenant):  # bare data-center host without a recruiting path
        return None
    site = _first_site_segment(parsed.path)
    if not site:
        return None
    return WorkdayCoords(host=host, tenant=tenant, site=site)


def is_workday_url(url: str | None) -> bool:
    """True if ``url`` is hosted on a genuine Workday board host."""

    if not url:
        return False
    host = _workday_host(url)
    return any(host.endswith(suffix) for suffix in _WD_HOST_SUFFIXES)
