"""Exporter port.

Abstraction over 'render ranked jobs to a file'. Phase 10 implements
``ExcelExporter`` (openpyxl, conditional formatting). Keeping this an interface
leaves room for CSV/PDF/HTML exporters later with no pipeline changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import Any


class Exporter(ABC):
    """Render a collection of ranked job records to a file on disk."""

    #: File extension produced, e.g. ``"xlsx"``.
    extension: str = "bin"

    @abstractmethod
    def export(self, jobs: Sequence[dict[str, Any]], destination: Path) -> Path:
        """Write ``jobs`` to ``destination`` and return the written path."""
