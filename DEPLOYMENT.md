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

**Port binding.** The container binds to `$PORT` (Render injects it; defaults to
`8000` locally): `uvicorn … --port ${PORT:-8000}`. `exec` is used so uvicorn is
PID 1 and receives `SIGTERM` for graceful shutdown.

**Fail-fast.** In `production` the app refuses to boot if `JOBAGENT_MONGO__URI`
is missing or still the local default — a misconfigured deploy crashes loudly
rather than running degraded. Set the real Atlas URI as a secret.

### Health & metrics

- `GET /health` — liveness (cheap, no external calls)
- `GET /health/live` — liveness alias (Render/Kubernetes-style livenessProbe)
- `GET /health/ready` — readiness (pings Mongo; 503 when a hard dep is down)
- `GET /metrics` — JSON or `?format=prometheus`

### CORS

Cross-origin is denied by default in production and allow-all in debug. To
allowlist origins, set `JOBAGENT_CORS_ORIGINS='["https://your-frontend"]'`.

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

**What the daily run does** (`app/scheduler/daily_pipeline.py`): loads the
source registry + active companies → routes companies to collectors → collects
postings → normalize → filter (seniority/role/experience/freshness/location) →
deduplicate → embed → rank → store → generate report → email. Each run is:

- **Idempotent** — a second run on a day that already succeeded is skipped
  (recovers safely after a restart/retry).
- **Audited** — one `SchedulerRun` document per run in the `scheduler_logs`
  collection (status, counts, failures, duration), surviving log expiry.
- **Graceful** — collector failures are isolated (one bad board never breaks the
  batch); a hard failure is recorded and the process exits non-zero.

The pipeline is also runnable on-demand: `job-agent-daily` (console script) or
`python -m app.scheduler.run_daily`.

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

## 6. Monitoring & observability

- **Logs:** structured JSON in production (`JOBAGENT_LOG_JSON=true`), with
  correlation IDs on every request and 10 MB rotation / 14-day retention / zip
  compression for file sinks. View live logs in the Render dashboard.
- **Metrics:** `GET /metrics` (JSON, or `?format=prometheus`) exposes request
  counts and embedding/latency summaries — scrape with Prometheus or Render
  metrics.
- **Run history:** query the `scheduler_logs` and `pipeline_runs` collections,
  or `GET /pipeline/stats` and `GET /pipeline/history`, for per-run outcomes.

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| App exits on boot with "JOBAGENT_MONGO__URI must point at a real cluster" | Prod fail-fast: URI unset/default | Set the real Atlas URI secret |
| `/health/ready` returns 503 | Mongo unreachable | Check Atlas network access + URI/credentials |
| Vector search returns nothing | Vector index missing/not READY | `job-agent-bootstrap --with-vector-index`; check Atlas → Search |
| Deploy healthy but port errors | Not binding `$PORT` | Ensure the shipped `Dockerfile` CMD (uses `${PORT:-8000}`) is unchanged |
| Daily run sends no email | `JOBAGENT_SMTP__TO_ADDRESS` unset, or bad App Password | Set/rotate SMTP secrets; check `scheduler_logs.failures` |
| Daily run "skipped" | Idempotency: already succeeded today | Expected; it prevents duplicate sends |

---

## 8. Failure recovery & rollback

- **Restart recovery:** the daily run is idempotent — a re-run after a crash on a
  day that already succeeded is skipped; a failed/partial run re-executes.
- **Degraded dependencies:** the API never crashes when Mongo/SMTP are down at
  runtime — readiness reports 503 and the affected operation fails gracefully.
- **Rollback:** Render keeps prior deploys — roll back from the dashboard. For a
  bad release, revert the offending commit on `main`; autodeploy ships the
  previous good state.
