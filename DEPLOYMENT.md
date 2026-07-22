# Deployment Guide

This guide covers deploying the AI Job Intelligence Agent to **Render** (API),
**MongoDB Atlas** (data + vector search), and **GitHub Actions** (daily
pipeline + CI). No secret is ever committed — all credentials are injected as
encrypted environment variables.

---

## 1. MongoDB Atlas

1. Create a cluster (**M10+** recommended for Vector Search).
2. **Database Access →** create a database user with a strong password.
3. **Network Access →** allow your deployment egress IPs (or `0.0.0.0/0` for a
   quick start; tighten for production).
4. Copy the SRV connection string; you will set it as `JOBAGENT_MONGO__URI`.
5. Set the database name: `JOBAGENT_MONGO__DB_NAME=job_intelligence`.
6. Create indexes and the vector index:
   ```bash
   job-agent-bootstrap --with-vector-index
   ```
   Or create the vector index manually (Atlas → Search → Create Index → JSON
   editor) using the definition in `app/db/indexes.py`: 384 dims, `cosine`,
   filter fields `status`, `work_mode`, `location_tags`.

---

## 2. SMTP (email notifications)

Gmail example:

1. Enable 2-Step Verification on the account.
2. Create an **App Password** (Google Account → Security → App Passwords).
3. Provide these as secrets (never in code):
   - `JOBAGENT_SMTP__HOST=smtp.gmail.com`
   - `JOBAGENT_SMTP__PORT=587`
   - `JOBAGENT_SMTP__USERNAME=<sender@gmail.com>`
   - `JOBAGENT_SMTP__PASSWORD=<app-password>`
   - `JOBAGENT_SMTP__TO_ADDRESS=<recipient>`

---

## 3. Render (API web service)

The repo ships a Render Blueprint (`render.yaml`) using the Docker runtime.

1. In Render, **New → Blueprint** and point it at this repository.
2. Render reads `render.yaml` and provisions the `ai-job-intelligence-agent`
   web service (health check `/health`, autodeploy on).
3. Set the `sync: false` secrets in the dashboard:
   - `JOBAGENT_MONGO__URI`
   - `JOBAGENT_SMTP__USERNAME`
   - `JOBAGENT_SMTP__PASSWORD`
   - `JOBAGENT_SMTP__TO_ADDRESS`
4. Non-secret settings (`JOBAGENT_ENV=production`, `JOBAGENT_LOG_JSON=true`,
   `JOBAGENT_VECTOR__BACKEND=atlas`, embedding model) are declared in
   `render.yaml`.

The Docker image (`Dockerfile`) is a lean multi-stage build running as a
non-root user, with a container-level `HEALTHCHECK` against `/health`. The ML
stack is intentionally excluded from the API image; the pipeline installs
`requirements-ml.txt` separately.

### Health & metrics

- `GET /health` — liveness
- `GET /health/ready` — readiness (pings Mongo)
- `GET /metrics` — JSON or `?format=prometheus`

---

## 4. GitHub Actions

### CI (`.github/workflows/ci.yml`)

Runs on every push to `main` and every PR: `ruff check` → `mypy` → `pytest`.

### Daily pipeline (`.github/workflows/daily.yml`)

Runs at **00:30 UTC (06:00 IST)** and on manual dispatch. Add these **encrypted
repository secrets** (Settings → Secrets and variables → Actions):

- `JOBAGENT_MONGO_URI`
- `JOBAGENT_SMTP_USERNAME`
- `JOBAGENT_SMTP_PASSWORD`
- `JOBAGENT_SMTP_TO_ADDRESS`

The workflow installs `requirements.txt` + `requirements-ml.txt`, caches the
embedding model, runs `python -m app.scheduler.run_daily`, and uploads logs on
failure.

---

## 5. Deployment checklist

- [ ] Atlas cluster reachable; user + network rules set
- [ ] Vector index created (`job-agent-bootstrap --with-vector-index`)
- [ ] Render secrets set (`sync: false` vars)
- [ ] GitHub Actions secrets set
- [ ] `/health` returns 200 after first deploy
- [ ] Daily workflow dispatched once manually to verify end-to-end
- [ ] No secrets in the repository (`.env` git-ignored)

---

## 6. Rollback

Render keeps prior deploys — roll back from the dashboard. For a bad release,
revert the offending commit on `main`; autodeploy ships the previous good state.
