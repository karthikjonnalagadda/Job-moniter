# Extensibility Guide

The AI Job Intelligence Agent is built on Clean/Hexagonal architecture (see `adr/ADR-002-clean-hexagonal.md`) precisely so that future capability lands as **new adapters, services, and routes behind existing ports** — not as a redesign. Every planned module below hangs off a port or package that already exists. Adding one means implementing an interface, registering an adapter, persisting through a repository, and (optionally) exposing a route or feature flag — with the pure domain in `app/core` left untouched.

## Module → Extension Point Map

| Future Module | Extension Point (port / package) | New code required |
|---|---|---|
| Resume Tailoring | `app/services/` orchestration + `EmbeddingProvider` (`app/embeddings`) | `ResumeTailoringService` that diffs resume vs. job embeddings and rewrites sections; no new port |
| AI Cover Letter Generator | `app/services/` + LLM adapter behind a service | `CoverLetterService` consuming job + resume documents; optional `Exporter` for output format |
| Application Tracker | Repository under `app/db/repositories` + `app/services/` | `ApplicationRepository`, `Application` Pydantic model, `ApplicationTrackerService`; FastAPI routes for CRUD |
| Resume Versioning | Repository under `app/db/repositories` | `ResumeVersionRepository` + versioned `Resume` model; reuse existing embedding pipeline per version |
| Skill Gap Analysis | `EmbeddingProvider` (`app/embeddings`) + `VectorScorer` (`app/vector`) + `app/services/` | `SkillGapService` comparing resume vs. job/skill embeddings; read-only aggregation |
| Company Intelligence | `BaseCollector` plugin + registry (`app/collectors`) + company sub-documents | New collector(s) enriching company records; `CompanyIntelligenceService` |
| Interview Tracker | Repository under `app/db/repositories` + `app/services/` | `InterviewRepository`, `Interview` model, `InterviewTrackerService`; FastAPI routes |
| Weekly Reports | `Exporter` port (`app/exporters/base.py`) + `app/services/` | `WeeklyReportExporter` + aggregation service; scheduled via GitHub Actions like the daily run |
| Dashboard | New FastAPI routes under `app/api/routes` + `Exporter` for data export | Route handlers + read-model services; no domain change |
| Telegram Notifications | `Notifier` port (`app/notifications/base.py`) | `TelegramNotifier` adapter + config/secret entry |
| Slack Notifications | `Notifier` port (`app/notifications/base.py`) | `SlackNotifier` adapter + config/secret entry |
| WhatsApp Notifications | `Notifier` port (`app/notifications/base.py`) | `WhatsAppNotifier` adapter + config/secret entry |
| Discord Notifications | `Notifier` port (`app/notifications/base.py`) | `DiscordNotifier` adapter + config/secret entry |
| Resume Analytics | Read-model aggregation service in `app/services/` over existing collections | `ResumeAnalyticsService`; optional dashboard route |
| Hiring Trend Analytics | Read-model aggregation service in `app/services/` over job collections | `HiringTrendService` (time-series aggregation pipelines); optional route/export |
| Salary Analytics | Read-model aggregation service in `app/services/` over job/company data | `SalaryAnalyticsService`; optional route/export |
| Company Recommendation Engine | `EmbeddingProvider` (`app/embeddings`) + `VectorScorer` (`app/vector`) | `CompanyRecommendationService` doing vector similarity over company/job embeddings |

All modules are gated through the **MongoDB `config` collection + feature flags**, so a new module can ship dark and be enabled per-environment without a redeploy.

## Recipe: Add a New Notification Channel
1. Implement the `Notifier` port from `app/notifications/base.py` in a new adapter (e.g. `app/notifications/telegram.py`).
2. Read channel credentials from settings/secrets; keep transport details inside the adapter.
3. Register the adapter so the notification dispatcher can resolve it, and add a feature flag in the `config` collection to enable it.
4. Add unit tests with a fake transport — no live channel needed because the domain only sees the `Notifier` interface.

## Recipe: Add a New Collector Source
1. Subclass `BaseCollector` under `app/collectors/` (e.g. `app/collectors/ashby.py`).
2. Set its `legal_mode` (`api` | `feed` | `scrape`) per ADR-003; `scrape` sources default to opt-in and must be robots-aware.
3. Register it in the collector **registry** so it is discovered by the daily run; return normalised job documents so dedup and embedding stay source-agnostic.
4. Add fixtures/tests against recorded payloads; no domain code changes.

## Recipe: Add a New Export / Report Type
1. Implement the `Exporter` port from `app/exporters/base.py` (e.g. `app/exporters/weekly_report.py`).
2. Build the report from an aggregation/read-model service in `app/services/` rather than querying collections from the exporter.
3. Wire it to a trigger — a GitHub Actions cron workflow for scheduled reports, or a FastAPI route under `app/api/routes` for on-demand download.
4. Reuse the existing `Notifier` to deliver the artifact if it should be pushed to users.

## Recipe: Add a New Analytics Module
1. Create a **read-model aggregation service** in `app/services/` that runs MongoDB aggregation pipelines over existing collections — analytics are read-only and never mutate operational data.
2. If similarity is involved (skill gap, recommendations), depend on `EmbeddingProvider` and `VectorScorer` rather than reimplementing scoring.
3. Expose results through a new route under `app/api/routes` and/or an `Exporter`, gated by a feature flag in the `config` collection.
4. Because it reads existing collections behind services, it requires no schema migration and no change to collectors or the domain core.
