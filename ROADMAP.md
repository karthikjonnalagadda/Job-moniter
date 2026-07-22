# Roadmap

This roadmap lists planned and potential future work. It is directional, not a
commitment, and nothing here is in progress on the current release.

## Now — `v0.8.x` (production-ready core)

- [x] Clean / Hexagonal architecture, DI container
- [x] Official-source ATS collectors
- [x] Pre-ranking filter chain (freshness, experience, seniority, role)
- [x] Semantic ranking + explainable composite score
- [x] Skill-gap analysis
- [x] Company classification & priority tiers
- [x] Multi-format reporting (HTML/XLSX/CSV/JSON/PDF)
- [x] SMTP notifications + daily GitHub Actions pipeline
- [x] Docker + Render Blueprint + CI

## Next — data coverage & reliability

- [ ] Widen ATS token coverage (Lever/Greenhouse/Workday) to grow the real
      entry-level pool.
- [ ] Collector health monitoring and dead-token pruning.
- [ ] Retry-queue / dead-letter observability.

## Later — product surface

- [ ] Web dashboard for browsing ranked matches and skill-gaps.
- [ ] Additional notification channels (Telegram, Slack).
- [ ] Multi-user profiles and per-user scheduling.
- [ ] Configurable ranking presets.

## Exploratory

- [ ] LLM-assisted resume parsing and job-description summarization.
- [ ] Salary normalization and market analytics.

> Have an idea? Open an issue to discuss it before starting work.
