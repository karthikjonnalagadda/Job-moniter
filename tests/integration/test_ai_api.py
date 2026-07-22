"""Phase-8 AI API surface (all 9 endpoints) against the in-memory app."""

from __future__ import annotations


def _seed_jobs(client) -> list[dict]:  # type: ignore[no-untyped-def]
    payload = {
        "items": [
            {
                "external_id": "1", "title": "Python Engineer", "company": "Acme",
                "url": "https://acme/1", "location": "Bangalore",
                "description": "Build APIs with Python and FastAPI",
            },
            {
                "external_id": "2", "title": "Java Engineer", "company": "Globex",
                "url": "https://globex/2", "location": "Remote",
                "description": "Enterprise Java and Spring services",
            },
        ],
        "resume": {"resume_id": "backend", "text": "python fastapi", "skills": ["Python"]},
        "persist": True,
    }
    resp = client.post("/pipeline/process", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["jobs"]


def test_models_and_health(app_client) -> None:
    models = app_client.get("/ai/models")
    assert models.status_code == 200
    body = models.json()
    # Active model depends on whether the optional ``ml`` extra is installed:
    # hashing fallback without it, BAAI/bge-small-en-v1.5 with it.
    assert body["active"]["name"] in ("hashing", "BAAI/bge-small-en-v1.5")
    assert any(m["name"] == "BAAI/bge-small-en-v1.5" for m in body["models"])

    health = app_client.get("/ai/models/health")
    assert health.status_code == 200
    hbody = health.json()
    assert hbody["healthy"] is True
    assert hbody["components"]["embedding_model"] is True


def test_metrics_endpoint(app_client) -> None:
    resp = app_client.get("/ai/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert "cache" in body and "models" in body and "device" in body


def test_embed_endpoint(app_client) -> None:
    resp = app_client.post("/ai/embed", json={"texts": ["python", "rust"], "is_query": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["dimensions"] == 384
    assert len(body["vectors"]) == 2

    # query mode + no vectors returned
    q = app_client.post(
        "/ai/embed", json={"texts": ["resume"], "is_query": True, "include_vectors": False}
    )
    assert q.status_code == 200 and q.json()["vectors"] == []


def test_skill_gap_endpoint(app_client) -> None:
    resp = app_client.post(
        "/ai/skill-gap",
        json={
            "resume_skills": ["Python"],
            "job_skills": ["Python", "Docker"],
            "job_technologies": ["Docker"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] == ["Python"]
    assert body["missing"] == ["Docker"]
    assert body["learning_priority"][0]["resources"]


def test_resume_embed_endpoint_diff_detection(app_client) -> None:
    first = app_client.post(
        "/ai/resume/embed", json={"resume_id": "ai", "content": "python fastapi"}
    )
    assert first.status_code == 200 and first.json()["regenerated"] is True
    again = app_client.post(
        "/ai/resume/embed", json={"resume_id": "ai", "content": "python fastapi"}
    )
    assert again.json()["regenerated"] is False


def test_vector_search_and_rerank_and_explain(app_client) -> None:
    jobs = _seed_jobs(app_client)
    job_hash = jobs[0]["job_hash"]

    search = app_client.post("/ai/vector-search", json={"text": "python engineer", "limit": 5})
    assert search.status_code == 200
    sbody = search.json()
    assert sbody["total"] >= 1
    assert sbody["hits"][0]["job"] is not None

    rerank = app_client.post(
        "/ai/rerank",
        json={
            "resume": {"resume_id": "backend", "text": "python", "skills": ["Python"]},
            "limit": 10,
        },
    )
    assert rerank.status_code == 200
    assert len(rerank.json()) >= 1

    explain = app_client.post(
        "/ai/explain",
        json={
            "resume": {"resume_id": "backend", "text": "python", "skills": ["Python"]},
            "job_hash": job_hash,
        },
    )
    assert explain.status_code == 200
    ebody = explain.json()
    assert "semantic" in ebody["explanations"]
    assert ebody["narrative"]


def test_vector_search_requires_input(app_client) -> None:
    resp = app_client.post("/ai/vector-search", json={"limit": 5})
    assert resp.status_code == 422


def test_explain_unknown_job_404(app_client) -> None:
    resp = app_client.post(
        "/ai/explain",
        json={"resume": {"skills": ["Python"]}, "job_hash": "does-not-exist"},
    )
    assert resp.status_code == 404
