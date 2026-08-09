"""Deterministic collection-status classification for company records.

Pure helpers (no I/O) shared by the maintenance scripts. They answer two
questions from fields already on a record:

* ``has_ats_collection_path`` — can a *registered* ATS collector fetch this
  company from stored coordinates? (Workday needs tenant+site; the token-based
  boards need a board token.) When true, collection should prefer the ATS over
  the corporate career page even if that page is WAF-blocked or dead.
* ``is_dead_endpoint`` — is the career URL a hard, permanent failure
  (404/410/invalid), as opposed to a transient hiccup (timeout, 5xx) or a soft
  block (WAF) that may still be reachable another way?

``compute_active_status`` combines them: a record is inactive only when its
career page is permanently dead *and* there is no ATS fallback — so nothing
collectible is ever switched off.
"""

from __future__ import annotations

from typing import Any

# ATS platforms whose registered collector needs only a flat board token.
_TOKEN_COLLECTORS = frozenset(
    {
        "greenhouse", "lever", "ashby", "smartrecruiters", "jobvite", "comeet",
        "workable", "bamboohr", "teamtailor", "recruitee", "breezyhr", "jazzhr",
    }
)
# career_status values that mean the endpoint is permanently gone.
_HARD_DEAD = frozenset({"not_found", "invalid", "broken"})


def _real(value: Any) -> bool:
    """True if a field holds a meaningful value (not blank/Unknown/None)."""

    return str(value or "").strip().lower() not in ("", "unknown", "none")


def has_ats_collection_path(rec: dict[str, Any]) -> bool:
    """True if a registered ATS collector can fetch this company from stored data."""

    platform = str(rec.get("ats_platform") or "").strip().lower()
    if platform == "workday":
        return _real(rec.get("ats_tenant")) and _real(rec.get("ats_board"))
    if platform in _TOKEN_COLLECTORS:
        return _real(rec.get("ats_token"))
    return False


def is_dead_endpoint(rec: dict[str, Any]) -> bool:
    """True if the career URL is a hard, permanent failure (not transient/blocked)."""

    return str(rec.get("career_status") or "").strip().lower() in _HARD_DEAD


def compute_active_status(rec: dict[str, Any]) -> bool:
    """A record stays active unless its page is permanently dead with no ATS fallback."""

    return not (is_dead_endpoint(rec) and not has_ats_collection_path(rec))
