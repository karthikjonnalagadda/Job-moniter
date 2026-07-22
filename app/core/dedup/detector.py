"""Multi-layer duplicate detection.

A candidate job is compared against the set of jobs already accepted this run
through five layers, highest-precision first:

    Layer 1 — identity hash   (company + role + location + apply URL)     conf 1.00
    Layer 5 — URL normalize   (same posting URL, tracking params stripped) conf 0.98
    Layer 2 — content hash    (order-insensitive title+description tokens)  conf 0.95
    Layer 4 — company alias   (same canonical company + role + location)    conf 0.90
    Layer 3 — semantic        (embedding cosine / token Jaccard ≥ threshold) conf = score

The first layer that fires wins; its confidence is the ``DuplicateConfidence``.
Layer 4 folds company aliases (Google/Alphabet, Meta/Facebook) *before*
comparison, so the same role at two names for one company is caught.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from app.core.dedup.hashing import content_fingerprint, job_hash, normalize_url, token_set
from app.core.similarity import cosine, jaccard
from app.models.base import AppBaseModel

if TYPE_CHECKING:
    from app.embeddings.provider import EmbeddingProvider
    from app.importers.aliases import AliasResolver
    from app.models.job import Job

_SEMANTIC_THRESHOLD = 0.9


class DuplicateVerdict(AppBaseModel):
    """Outcome of checking one job against the accepted set."""

    is_duplicate: bool
    confidence: float = 0.0  # DuplicateConfidence in [0, 1]
    layer: str | None = None  # which layer fired
    matched_hash: str | None = None  # job_hash of the original
    reason: str = ""


class DedupResult(AppBaseModel):
    """Aggregate result of de-duplicating a batch."""

    unique: int
    duplicates: int
    verdicts: list[DuplicateVerdict] = Field(default_factory=list)


class _Seen(AppBaseModel):
    job_hash: str
    url: str
    fingerprint: str
    canonical_key: str  # canonical_company | role | location
    tokens: list[str]
    embedding: list[float] | None = None


class DuplicateDetector:
    """Detects duplicates across a batch using five layers."""

    def __init__(
        self,
        *,
        aliases: AliasResolver | None = None,
        semantic_threshold: float = _SEMANTIC_THRESHOLD,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self._aliases = aliases
        self._threshold = semantic_threshold
        # Optional: when set, Layer 3 compares real embeddings (computed on the
        # fly for jobs lacking one) instead of falling back to token Jaccard —
        # sharper near-duplicate detection. Opt-in; default flow is unchanged.
        self._embedder = embedder
        self._seen: list[_Seen] = []
        self._by_hash: dict[str, _Seen] = {}
        self._by_url: dict[str, _Seen] = {}
        self._by_fingerprint: dict[str, _Seen] = {}
        self._by_canonical: dict[str, _Seen] = {}

    # ---- canonicalisation ----------------------------------------------
    def _canonical_company(self, job: Job) -> str:
        name = job.canonical_company_name or job.company_name
        if self._aliases is not None:
            match = self._aliases.resolve(job.company_name)
            if match is not None:
                name = match[1]
        return " ".join(name.lower().split())

    def _record_for(self, job: Job) -> _Seen:
        role = (job.normalized_role or job.role or "").lower().strip()
        location = (job.location.city or "") + "|" + (job.location.country or "")
        canonical_key = f"{self._canonical_company(job)}|{role}|{location.lower()}"
        return _Seen(
            job_hash=job.job_hash or job_hash(job.company_name, job.role, location, job.url),
            url=normalize_url(job.url),
            fingerprint=job.content_fingerprint or content_fingerprint(job.role, job.description),
            canonical_key=canonical_key,
            tokens=sorted(token_set(job.role, job.description)),
            embedding=job.embedding,
        )

    # ---- checking ------------------------------------------------------
    def check(self, job: Job) -> DuplicateVerdict:
        """Compare ``job`` to everything accepted so far (does not record it)."""

        record = self._record_for(job)

        if record.job_hash in self._by_hash:
            return self._hit("layer1_hash", 1.0, self._by_hash[record.job_hash], "identical key")
        if record.url and record.url in self._by_url:
            return self._hit("layer5_url", 0.98, self._by_url[record.url], "same posting URL")
        if record.fingerprint and record.fingerprint in self._by_fingerprint:
            return self._hit(
                "layer2_fingerprint", 0.95, self._by_fingerprint[record.fingerprint], "same content"
            )
        if record.canonical_key in self._by_canonical:
            return self._hit(
                "layer4_alias", 0.90, self._by_canonical[record.canonical_key], "same company+role"
            )
        semantic = self._semantic_match(record)
        if semantic is not None:
            match, score = semantic
            return self._hit("layer3_semantic", round(score, 4), match, "semantically similar")
        return DuplicateVerdict(is_duplicate=False)

    def _semantic_match(self, record: _Seen) -> tuple[_Seen, float] | None:
        best: tuple[_Seen, float] | None = None
        candidate_tokens = set(record.tokens)
        if record.embedding is None and self._embedder is not None:
            # Fill a transient embedding for sharper Layer-3 comparison.
            record.embedding = self._embedder.embed_documents([" ".join(record.tokens)])[0]
        for seen in self._seen:
            if record.embedding and seen.embedding:
                score = cosine(record.embedding, seen.embedding)
            else:
                score = jaccard(candidate_tokens, set(seen.tokens))
            if score >= self._threshold and (best is None or score > best[1]):
                best = (seen, score)
        return best

    def accept(self, job: Job) -> _Seen:
        """Record ``job`` as an accepted (unique) posting for future checks."""

        record = self._record_for(job)
        self._seen.append(record)
        self._by_hash.setdefault(record.job_hash, record)
        if record.url:
            self._by_url.setdefault(record.url, record)
        if record.fingerprint:
            self._by_fingerprint.setdefault(record.fingerprint, record)
        self._by_canonical.setdefault(record.canonical_key, record)
        return record

    def deduplicate(self, jobs: list[Job]) -> tuple[list[Job], DedupResult]:
        """Return (unique jobs, result). Duplicates get a ``match`` verdict recorded."""

        unique: list[Job] = []
        verdicts: list[DuplicateVerdict] = []
        duplicates = 0
        for job in jobs:
            verdict = self.check(job)
            verdicts.append(verdict)
            if verdict.is_duplicate:
                duplicates += 1
                continue
            self.accept(job)
            unique.append(job)
        return unique, DedupResult(
            unique=len(unique), duplicates=duplicates, verdicts=verdicts
        )

    @staticmethod
    def _hit(layer: str, confidence: float, match: _Seen, reason: str) -> DuplicateVerdict:
        return DuplicateVerdict(
            is_duplicate=True,
            confidence=confidence,
            layer=layer,
            matched_hash=match.job_hash,
            reason=reason,
        )
