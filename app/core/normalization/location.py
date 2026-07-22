"""Location normalization — free-text location → canonical ``Location``.

Resolves city aliases (Bengaluru → Bangalore), work mode (WFH → remote), and
country, populating a ``Location`` value object plus ``location_tags`` used as a
vector-search filter field.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.normalization.taxonomy import SynonymIndex, load_yaml
from app.models.common import Location
from app.models.enums import WorkMode

_DEFAULT_CITIES = {
    "Bangalore": ["bengaluru", "bangalore", "blr"],
    "Mumbai": ["mumbai", "bombay"],
    "Hyderabad": ["hyderabad", "hyd"],
    "Remote": ["remote"],
}
_DEFAULT_WORK_MODES = {
    "remote": ["remote", "wfh", "work from home", "anywhere"],
    "hybrid": ["hybrid"],
    "onsite": ["onsite", "on-site", "in office"],
}
_DEFAULT_COUNTRIES = {"IN": ["india", "in"], "US": ["united states", "usa", "us"]}


class LocationNormalizer:
    """Normalise a raw location string into a canonical ``Location``."""

    def __init__(
        self,
        cities: SynonymIndex,
        work_modes: SynonymIndex,
        countries: SynonymIndex,
    ) -> None:
        self._cities = cities
        self._work_modes = work_modes
        self._countries = countries

    @classmethod
    def from_file(cls, path: Path | None) -> LocationNormalizer:
        data = load_yaml(path) or {}
        cities = data.get("cities") if isinstance(data, dict) else None
        work_modes = data.get("work_modes") if isinstance(data, dict) else None
        countries = data.get("countries") if isinstance(data, dict) else None
        return cls(
            SynonymIndex(_as_mapping(cities, _DEFAULT_CITIES)),
            SynonymIndex(_as_mapping(work_modes, _DEFAULT_WORK_MODES)),
            SynonymIndex(_as_mapping(countries, _DEFAULT_COUNTRIES)),
        )

    def normalize(self, raw: str | None) -> Location:
        if not raw or not str(raw).strip():
            return Location()
        text = str(raw).strip()

        work_mode_key = self._work_modes.find_first(text)
        work_mode = WorkMode.UNKNOWN
        if work_mode_key and work_mode_key in {m.value for m in WorkMode}:
            work_mode = WorkMode(work_mode_key)
        is_remote = work_mode == WorkMode.REMOTE

        city = self._cities.find_first(text)
        country = self._countries.find_first(text)

        return Location(
            raw=text,
            city=None if city == "Remote" else city,
            country=country,
            work_mode=work_mode,
            is_remote=is_remote or city == "Remote",
        )

    def tags(self, location: Location) -> list[str]:
        tags: list[str] = []
        if location.is_remote:
            tags.append("remote")
        if location.city:
            tags.append(location.city.lower())
        if location.country:
            tags.append(location.country.lower())
        return tags


def _as_mapping(value: Any, fallback: dict[str, list[str]]) -> dict[str, list[str]]:
    if isinstance(value, dict) and value:
        return {str(k): [str(s) for s in (v or [])] for k, v in value.items()}
    return fallback
