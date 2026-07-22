"""Small text utilities shared across importers and seeding."""

from __future__ import annotations

import re
import unicodedata

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Return a lowercase, hyphenated, ASCII slug for ``value``.

    Ampersands become ``and`` (so ``L&T`` -> ``l-and-t``); accents are folded;
    any remaining non-alphanumeric run collapses to a single hyphen.
    """

    text = unicodedata.normalize("NFKD", value)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ")
    text = _NON_SLUG.sub("-", text)
    return text.strip("-")
