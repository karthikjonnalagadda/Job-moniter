# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0] — 2026-07-22

First production-ready release.

### Added
- **Clean / Hexagonal architecture** with ports & adapters and dependency
  injection throughout.
- **ATS collectors** (Greenhouse, Lever, SmartRecruiters, Ashby, Workday, and
  more) reading from official sources only.
- **Pre-ranking filter chain** — freshness, experience, **seniority**, and
  **role-relevance** filters reject unsuitable roles before embedding.
- **Semantic ranking** on `BAAI/bge-small-en-v1.5` (384-dim) via MongoDB Atlas
  Vector Search, blended into a transparent 7-component composite score
  (similarity, skill, experience, location, company-priority, freshness,
  quality).
- **Explainable matches** with per-component sub-scores and narratives.
- **Skill-gap analysis** with technical-skill coverage and a prioritized
  learning list.
- **Company classification & priority tiers** (P1–P5).
- **Multi-format reporting** — HTML, Excel, CSV, JSON, PDF.
- **SMTP notifications** and a **daily GitHub Actions pipeline**.
- **FastAPI service** with health, readiness, metrics, and collector endpoints;
  correlation-ID middleware.
- **Indian company career-site dataset** builder and curated seed data.
- Docker image, `docker-compose`, and Render Blueprint.
- CI (ruff + mypy + pytest) and full unit/integration test coverage.

### Security
- All credentials are environment-provided; no secrets committed.
- `.env` git-ignored; `.env.example` template shipped.

[0.8.0]: https://github.com/karthikjonnalagadda/Job-moniter/releases/tag/v0.8.0
