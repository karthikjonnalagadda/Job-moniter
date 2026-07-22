"""Report themes — inline CSS palettes for HTML/email reports.

Inline CSS (no external assets) so reports render identically in a browser and
in email clients. Themes are selected by name; unknown names fall back to
``default``.
"""

from __future__ import annotations

_THEMES: dict[str, dict[str, str]] = {
    "default": {
        "bg": "#f4f6f9",
        "card": "#ffffff",
        "text": "#1f2933",
        "muted": "#66788a",
        "accent": "#1f4e78",
        "bar": "#2f80ed",
        "border": "#e3e8ee",
    },
    "dark": {
        "bg": "#0f1720",
        "card": "#1b2430",
        "text": "#e6edf3",
        "muted": "#9fb0c0",
        "accent": "#4f9cf9",
        "bar": "#4f9cf9",
        "border": "#2a3746",
    },
}


def theme(name: str = "default") -> dict[str, str]:
    return _THEMES.get(name, _THEMES["default"])


def theme_names() -> list[str]:
    return list(_THEMES)
