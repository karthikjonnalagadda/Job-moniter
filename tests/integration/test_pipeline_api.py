"""Pipeline API surface."""

from __future__ import annotations


def _item(i: int, title: str, company: str, desc: str) -> dict:
    return {
        "external_id": str(i),
        "title": title,
        "company": company,
        "url": f"https://boards.greenhouse.io/{company}/jobs/{i}",
        "location": "Bengaluru, India",
        "description": desc,
        "posted": "today",
        "source": "greenhouse",
        "ats_type": "greenhouse",
    }


def test_process_endpoint(app_client) -> None:
    body = {
        "items": [
            _item(1, "ML Engineer", "Google", "Python FastAPI PyTorch RAG. 0-2 years."),
            _item(2, "Senior Backend Engineer", "Flipkart", "8+ years Java Spring."),
        ],
        "resume": {"resume_id": "ai", "text": "Python FastAPI RAG", "max_experience_years": 2},
        "persist": True,
    }
    resp = app_client.post("/pipeline/process", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["run"]["collected"] == 2
    assert data["run"]["filtered_out"] == 1  # senior role dropped
    assert data["run"]["stored"] == 1
    assert data["jobs"][0]["match"]["score"] > 0
    assert data["jobs"][0]["match"]["explanations"]


def test_extract_skills_endpoint(app_client) -> None:
    resp = app_client.post(
        "/pipeline/extract-skills", json={"text": "Python, Docker, AWS, Kubernetes"}
    )
    assert resp.status_code == 200
    skills = resp.json()["skills"]
    assert "Python" in skills and "Docker" in skills


def test_deduplicate_endpoint(app_client) -> None:
    body = {
        "items": [
            _item(1, "ML Engineer", "Google", "Python FastAPI. 0-2 years."),
            _item(2, "Machine Learning Engineer", "Alphabet", "Python FastAPI. 0-2 years."),
        ]
    }
    resp = app_client.post("/pipeline/deduplicate", json=body)
    assert resp.status_code == 200
    assert resp.json()["duplicates"] == 1  # Google/Alphabet folded


def test_stats_and_history_endpoints(app_client) -> None:
    app_client.post(
        "/pipeline/process",
        json={"items": [_item(1, "ML Engineer", "Google", "Python. 0-2 years.")], "persist": True},
    )
    stats = app_client.get("/pipeline/stats").json()
    assert stats["total_jobs"] >= 1
    assert stats["total_runs"] >= 1
    history = app_client.get("/pipeline/history").json()
    assert len(history) >= 1
    assert history[0]["status"] == "success"


def test_rank_endpoint_reranks_stored(app_client) -> None:
    app_client.post(
        "/pipeline/process",
        json={"items": [_item(1, "ML Engineer", "Google", "Python FastAPI RAG. 0-2 years.")]},
    )
    resp = app_client.post(
        "/pipeline/rank",
        json={"resume": {"resume_id": "backend", "text": "Java Spring backend"}, "persist": True},
    )
    assert resp.status_code == 200
    jobs = resp.json()
    assert jobs and jobs[0]["match"]["resume_id"] == "backend"
