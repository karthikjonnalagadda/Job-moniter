"""ATS auto-detection from a company's career URL.

Given a career/careers URL, infer which ATS platform hosts it and, where the
URL encodes it, the board token/subdomain. This lets the router prefer a
first-class ATS collector over the generic career-site crawler, and lets the
import pipeline enrich ``Company.ats_type`` / ``ats_token`` automatically.

Detection is pattern-based and deterministic (no network calls). Each rule maps
a host/path signature to an ``ATSType`` plus a strategy for extracting the token:

    * ``subdomain`` — the token is the first DNS label (``acme`` in
      ``acme.bamboohr.com``);
    * ``path``      — the token is the first non-empty path segment
      (``acme`` in ``jobs.lever.co/acme``);
    * ``none``      — the platform is identifiable but the token is not encoded
      in the URL (e.g. Workday, whose tenant/site live deeper in the path).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from app.models.enums import ATSType

# Generic subdomains that are never a board token.
_GENERIC_LABELS = frozenset({"www", "careers", "career", "jobs", "job", "apply", "boards"})


@dataclass(frozen=True)
class ATSDetection:
    """Result of inspecting a career URL."""

    ats_type: ATSType
    token: str | None
    platform: str | None
    confidence: float  # 0.0-1.0

    @property
    def detected(self) -> bool:
        return self.ats_type != ATSType.UNKNOWN


@dataclass(frozen=True)
class _Rule:
    #: Substring that must appear in the URL host for the rule to fire.
    host_marker: str
    ats_type: ATSType
    platform: str
    token_strategy: str  # "subdomain" | "path" | "none"
    confidence: float = 0.95


# Order matters only for readability; markers are host-unique in practice.
_RULES: tuple[_Rule, ...] = (
    _Rule("greenhouse.io", ATSType.GREENHOUSE, "Greenhouse", "path"),
    _Rule("lever.co", ATSType.LEVER, "Lever", "path"),
    _Rule("ashbyhq.com", ATSType.ASHBY, "Ashby", "path"),
    _Rule("myworkdayjobs.com", ATSType.WORKDAY, "Workday", "none"),
    _Rule("myworkdaysite.com", ATSType.WORKDAY, "Workday", "none"),
    _Rule("smartrecruiters.com", ATSType.SMARTRECRUITERS, "SmartRecruiters", "path"),
    _Rule("bamboohr.com", ATSType.BAMBOOHR, "BambooHR", "subdomain"),
    _Rule("teamtailor.com", ATSType.TEAMTAILOR, "Teamtailor", "subdomain"),
    _Rule("recruitee.com", ATSType.RECRUITEE, "Recruitee", "subdomain"),
    _Rule("jobvite.com", ATSType.JOBVITE, "Jobvite", "path"),
    _Rule("icims.com", ATSType.ICIMS, "iCIMS", "subdomain"),
    _Rule("oraclecloud.com", ATSType.ORACLE, "Oracle Recruiting", "none"),
    _Rule("taleo.net", ATSType.ORACLE, "Oracle Taleo", "none"),
    _Rule("sapsf.com", ATSType.SUCCESSFACTORS, "SAP SuccessFactors", "none"),
    _Rule("sapsf.eu", ATSType.SUCCESSFACTORS, "SAP SuccessFactors", "none"),
    _Rule("successfactors.com", ATSType.SUCCESSFACTORS, "SAP SuccessFactors", "none"),
    _Rule("comeet.co", ATSType.COMEET, "Comeet", "path"),
    _Rule("comeet.com", ATSType.COMEET, "Comeet", "path"),
    _Rule("breezy.hr", ATSType.BREEZYHR, "BreezyHR", "subdomain"),
    _Rule("applytojob.com", ATSType.JAZZHR, "JazzHR", "subdomain"),
)

_UNKNOWN = ATSDetection(ATSType.UNKNOWN, None, None, 0.0)


def _subdomain_token(host: str) -> str | None:
    labels = [label for label in host.split(".") if label]
    if len(labels) < 3:  # no meaningful subdomain (e.g. "breezy.hr")
        return None
    first = labels[0]
    return first if first not in _GENERIC_LABELS else None


def _path_token(path: str) -> str | None:
    segments = [segment for segment in path.split("/") if segment]
    for segment in segments:
        if segment.lower() not in _GENERIC_LABELS:
            return segment
    return None


class ATSDetector:
    """Detect the ATS behind a career URL (pattern-based, no network)."""

    def detect(self, url: str | None) -> ATSDetection:
        if not url:
            return _UNKNOWN
        parsed = urlparse(url if "://" in url else f"https://{url}")
        host = parsed.netloc.lower()
        if not host:
            return _UNKNOWN
        for rule in _RULES:
            if rule.host_marker in host:
                token = self._extract_token(rule, host, parsed.path)
                # A platform we recognise but whose token we couldn't read is
                # still a useful (slightly lower-confidence) signal.
                confidence = rule.confidence if token or rule.token_strategy == "none" else 0.6
                return ATSDetection(rule.ats_type, token, rule.platform, confidence)
        return _UNKNOWN

    @staticmethod
    def _extract_token(rule: _Rule, host: str, path: str) -> str | None:
        if rule.token_strategy == "subdomain":
            return _subdomain_token(host)
        if rule.token_strategy == "path":
            return _path_token(path)
        return None
