"""Template system — Jinja2 rendering with theme + Markdown support.

Renders HTML (and Markdown) report templates from ``app/reports/templates``.
Themes inject an inline CSS palette (email-safe). Markdown rendering lazily
imports the optional ``markdown`` package (``reports`` extra); without it, a
minimal built-in converter keeps things working.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.reports.themes import theme

_TEMPLATE_DIR = Path(__file__).parent / "templates"


class TemplateRenderer:
    """Render report templates with a selected theme."""

    def __init__(self, template_dir: Path | None = None) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir or _TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._env.filters["comma"] = lambda n: f"{n:,}" if isinstance(n, int | float) else n

    def render(
        self, template_name: str, context: dict[str, Any], *, theme_name: str = "default"
    ) -> str:
        template = self._env.get_template(template_name)
        return template.render(**context, theme=theme(theme_name))

    def render_string(self, source: str, context: dict[str, Any]) -> str:
        return self._env.from_string(source).render(**context)

    @staticmethod
    def render_markdown(md_text: str) -> str:
        """Convert Markdown to HTML (lazy optional dependency + fallback)."""

        try:
            import markdown

            return markdown.markdown(md_text, extensions=["tables"])
        except ImportError:
            # Minimal fallback: paragraphs only (keeps reports working sans extra).
            paragraphs = [p.strip() for p in md_text.split("\n\n") if p.strip()]
            return "\n".join(f"<p>{p}</p>" for p in paragraphs)
