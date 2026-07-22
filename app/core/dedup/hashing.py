"""Hashing + fingerprint primitives for duplicate detection.

* ``job_hash`` — Layer 1 identity key: company + role + location + apply URL,
  normalised and SHA-256'd. This is the unique ``jobs.job_hash`` index key.
* ``content_fingerprint`` — Layer 2: an order-insensitive hash of the significant
  tokens in title + description, so re-posts with shuffled/edited wording still
  collide.
* ``normalize_url`` — Layer 5: canonicalise a posting URL (drop scheme/query/
  fragment/trailing slash, lowercase host) so tracking params don't defeat dedup.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {"the", "a", "an", "and", "or", "for", "of", "to", "in", "at", "on", "with", "job", "role"}
)


def _norm(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(_WORD.findall(text.lower()))


def normalize_url(url: str | None) -> str:
    """Canonicalise a URL for comparison (Layer 5)."""

    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/").lower()
    return f"{host}{path}"


def job_hash(company: str | None, role: str | None, location: str | None, url: str | None) -> str:
    """Layer-1 identity hash from the key fields."""

    key = "|".join((_norm(company), _norm(role), _norm(location), normalize_url(url)))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _significant_tokens(text: str) -> list[str]:
    return [tok for tok in _norm(text).split() if tok not in _STOPWORDS and len(tok) > 1]


def content_fingerprint(*parts: str | None) -> str:
    """Layer-2 order-insensitive content hash of the significant tokens."""

    tokens = sorted({tok for part in parts for tok in _significant_tokens(part or "")})
    if not tokens:
        return ""
    return hashlib.sha256(" ".join(tokens).encode("utf-8")).hexdigest()


def token_set(*parts: str | None) -> set[str]:
    """Significant-token set (used for Jaccard content similarity, Layer 2/3)."""

    return {tok for part in parts for tok in _significant_tokens(part or "")}
