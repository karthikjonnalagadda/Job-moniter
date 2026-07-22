"""Compatibility shim — ``ImportRecord`` lives in ``app.importers.records``.

Kept so ``from app.models.import_record import ImportRecord`` still resolves.
The canonical definition is in the importers package to avoid a circular import
(``ImportRecord`` embeds ``ImportStats``).
"""

from __future__ import annotations

from app.importers.records import ImportRecord

__all__ = ["ImportRecord"]
