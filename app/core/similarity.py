"""Vector/set similarity helpers shared by dedup (Layer 3) and ranking."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def cosine(a: Sequence[float] | None, b: Sequence[float] | None) -> float:
    """Cosine similarity in [0, 1] (negatives clamped to 0). 0 if either empty."""

    if not a or not b:
        return 0.0
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0.0:
        return 0.0
    return max(0.0, float(np.dot(va, vb) / denom))


def jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard overlap of two token sets in [0, 1]."""

    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0
