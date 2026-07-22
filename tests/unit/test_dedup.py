"""Duplicate detection: hashing primitives + 5-layer detector."""

from __future__ import annotations

from pathlib import Path

from app.core.dedup.detector import DuplicateDetector
from app.core.dedup.hashing import content_fingerprint, job_hash, normalize_url
from app.importers.aliases import AliasResolver
from app.models.job import Job

_ALIASES = AliasResolver.from_file(Path("data/company_aliases.yaml"))


def _job(**kw: object) -> Job:
    base: dict[str, object] = {
        "job_hash": "", "external_id": "1", "source": "greenhouse",
        "company_name": "Acme", "role": "Backend Engineer", "url": "https://x/1",
    }
    base.update(kw)
    return Job(**base)  # type: ignore[arg-type]


def test_hashing_primitives() -> None:
    assert normalize_url("https://www.X.com/a/?utm=1#frag") == "x.com/a"
    assert job_hash("Acme", "Eng", "NYC", "u") == job_hash("acme", "eng", "nyc", "u")
    assert content_fingerprint("A B C", "") == content_fingerprint("c b a", None)


def test_layer1_identical_hash() -> None:
    det = DuplicateDetector()
    a = _job(job_hash="same")
    det.deduplicate([a])
    verdict = det.check(_job(job_hash="same"))
    assert verdict.is_duplicate and verdict.layer == "layer1_hash" and verdict.confidence == 1.0


def test_layer4_company_alias() -> None:
    det = DuplicateDetector(aliases=_ALIASES)
    # Distinct URLs + descriptions (so layers 1/2/5 miss); same canonical company
    # (Google→Alphabet) + role + location, so only the alias layer fires.
    google = _job(
        company_name="Google", url="https://a/1", job_hash="g",
        description="Build web search ranking infrastructure at scale",
    )
    alphabet = _job(
        company_name="Alphabet", url="https://b/2", job_hash="a",
        description="Design distributed cloud storage control planes",
    )
    unique, result = det.deduplicate([google, alphabet])
    assert len(unique) == 1  # folded to one canonical company + role + location
    assert result.duplicates == 1
    assert result.verdicts[1].layer == "layer4_alias"


def test_layer3_semantic_via_embeddings() -> None:
    det = DuplicateDetector(semantic_threshold=0.95)
    a = _job(job_hash="1", url="https://a/1", embedding=[1.0, 0.0, 0.0])
    b = _job(  # different company/role/url but near-identical vector
        job_hash="2", url="https://a/2", company_name="Other", role="Different",
        embedding=[0.99, 0.01, 0.0],
    )
    unique, result = det.deduplicate([a, b])
    assert len(unique) == 1
    assert result.verdicts[1].layer == "layer3_semantic"


def test_unique_jobs_survive() -> None:
    det = DuplicateDetector()
    jobs = [
        _job(job_hash="1", url="https://a/1", role="Backend Engineer"),
        _job(job_hash="2", url="https://a/2", role="Frontend Engineer", company_name="Beta"),
    ]
    unique, result = det.deduplicate(jobs)
    assert len(unique) == 2 and result.duplicates == 0
