"""Collector/registry version compatibility.

``REGISTRY_VERSION`` is the version of the collector plugin contract the host
application implements. A collector declares ``minimum_registry_version`` (the
oldest contract it needs); ``is_compatible`` checks a collector against the host
so future upgrades can refuse to load incompatible plugins instead of failing
mysteriously at runtime.
"""

from __future__ import annotations

# Bump when the collector plugin contract changes in a breaking way.
REGISTRY_VERSION = "1.0.0"


def _parse(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in version.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def is_compatible(
    minimum_registry_version: str | None, host_version: str = REGISTRY_VERSION
) -> bool:
    """True if ``host_version`` satisfies the collector's minimum requirement."""

    if not minimum_registry_version:
        return True
    return _parse(host_version) >= _parse(minimum_registry_version)
