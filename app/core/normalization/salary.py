"""Salary normalization — free-text compensation → structured ``SalaryRange``.

Handles the conventions seen across Indian and global postings:

* currencies ``₹ $ € £`` (and words ``INR USD EUR GBP``);
* Indian magnitudes — ``LPA`` / ``CTC`` / ``lakh`` (1e5) / ``crore`` (1e7);
* ``k`` (1e3) suffix (per-number, e.g. ``$120k - $150k``);
* ranges and single figures;
* periods — annual / monthly / hourly.

Conservative: a number is only read as salary when it carries a salary *signal*
(a currency symbol/word, or a magnitude/period keyword). This stops experience
figures like ``"3+ years"`` from being mistaken for pay. Returns ``None`` when no
salary-bearing token is present.
"""

from __future__ import annotations

import re

from app.models.common import SalaryRange

_MAG = r"lpa|lakhs?|lacs?|crores?|cr|k"
_PERIOD = (
    r"lpa|ctc|per\s*annum|p\.?a\.?|/\s*yr|/\s*year|annually|"
    r"per\s*month|/\s*month|monthly|per\s*hour|/\s*hour|hourly"
)
_SALARY = re.compile(
    r"(?P<cur>₹|rs\.?|inr|\$|usd|€|eur|£|gbp)?\s*"
    r"(?P<n1>\d[\d,]*(?:\.\d+)?)\s*(?P<m1>" + _MAG + r")?"
    r"(?:\s*(?:-|to|–|—)\s*(?P<cur2>₹|\$|€|£)?\s*(?P<n2>\d[\d,]*(?:\.\d+)?)\s*(?P<m2>"
    + _MAG
    + r")?)?"
    r"\s*(?P<tail>" + _MAG + r"|" + _PERIOD + r")?",
    re.IGNORECASE,
)

_CURRENCY_CODE = {
    "₹": "INR", "rs": "INR", "rs.": "INR", "inr": "INR",
    "$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP",
}
_MAGNITUDE = {
    "crore": 1e7, "crores": 1e7, "cr": 1e7,
    "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "lpa": 1e5,
    "k": 1e3,
}


def _magnitude(token: str | None) -> float | None:
    if not token:
        return None
    return _MAGNITUDE.get(token.lower().replace(" ", ""))


def _period(tail: str) -> str:
    t = tail.lower().replace(" ", "")
    if "hour" in t or "/hr" in t:
        return "hour"
    if "month" in t:
        return "month"
    return "year"


class SalaryNormalizer:
    """Parse a free-text salary string into a ``SalaryRange``."""

    def parse(self, text: str | None) -> SalaryRange | None:
        if not text or not str(text).strip():
            return None
        raw = str(text).strip()
        for match in _SALARY.finditer(raw):
            cur = match.group("cur") or match.group("cur2")
            tail = match.group("tail") or ""
            if not cur and not match.group("m1") and not match.group("m2") and not tail:
                continue  # no salary signal — skip (likely an experience figure)
            return self._build(match, cur, tail, raw)
        return None

    def _build(
        self, match: re.Match[str], cur: str | None, tail: str, raw: str
    ) -> SalaryRange:
        mag1 = _magnitude(match.group("m1"))
        mag2 = _magnitude(match.group("m2"))
        # Range figures share units: an unmarked number inherits the other's
        # magnitude ("25-35 LPA" → both ×1e5; "$120k-$150k" → both ×1e3).
        shared = mag1 or mag2 or _magnitude(tail) or 1.0
        f1 = mag1 or shared
        f2 = mag2 or shared

        amounts = [float(match.group("n1").replace(",", "")) * f1]
        if match.group("n2"):
            amounts.append(float(match.group("n2").replace(",", "")) * f2)
        amounts.sort()

        currency = _CURRENCY_CODE.get(cur.lower()) if cur else None
        if currency is None and max(f1, f2) >= 1e5:
            currency = "INR"  # lakh/crore/LPA imply INR

        period = _period(tail) if tail and _magnitude(tail) is None else "year"
        return SalaryRange(
            min_amount=round(amounts[0], 2),
            max_amount=round(amounts[-1], 2) if len(amounts) > 1 else None,
            currency=currency,
            period=period,
            raw=raw,
        )
