# Reporting, Exporting & Notification Engine (Phase 7)

Turns processed jobs into professional reports and automated notifications. Built
entirely on the existing `Exporter` / `Notifier` ports plus a report-oriented
`ReportExporter`; no approved architecture was modified.

## Architecture

```
JobRepository ─┐
RunRepository ─┼─▶ AnalyticsService ─▶ ReportDatasetBuilder ─▶ ReportData ─┬─▶ ExcelExporter  (.xlsx)
BenchmarkRepo ─┘                                     (single assembled view) ├─▶ CsvExporter   (.csv/.gz/stream)
                                                                            ├─▶ JsonExporter  (pretty/compact/ndjson)
                                                                            ├─▶ HtmlExporter  (Jinja2 dashboard)
                                                                            └─▶ PdfExporter   (reportlab)
                                                                                     │
ReportService.generate(format) ──▶ writes file + ReportRecord (history + versions)  │
NotificationService.send_report ──▶ HTML body + attachments ─▶ Notifier(SMTP) ──────┘
```

`ReportData` is assembled **once** and shared by every format, so no exporter
recomputes anything.

### Report architecture
- `app/reports/dataset.py` — `ReportData` (the one view) + `ReportDatasetBuilder`.
- `app/reports/context.py` — flattens `ReportData` into a template context (shared by HTML/PDF/email).
- `app/reports/service.py` — `ReportService.generate(format)` → writes file + persists `ReportRecord`.
- `app/reports/versioning.py` — stamps `report_version` / `schema_version` / `pipeline_version` / `collector_versions` on every report.
- `app/reports/scheduling.py` — `ReportScheduler` (daily/weekly/monthly/manual due-logic).
- `app/reports/templating.py` + `templates/report.html.j2` + `themes.py` — Jinja2 + Markdown + themes.

### Exporter architecture
`app/exporters/` — `report_base.ReportExporter` (over `ReportData`) alongside the
existing row-oriented `Exporter` port. `rows.py` flattens a `Job` to a tabular row
(shared by CSV/JSON/Excel). `registry.build_exporter(format, **opts)` resolves a
format to a configured exporter.

| Format | Module | Highlights |
|---|---|---|
| Excel | `excel.py` | 9 sheets, frozen headers, auto width, auto-filters, Excel tables, match-score colour scale, apply hyperlinks, bar charts |
| CSV | `csv_exporter.py` | plain · gzip-compressed · streaming (constant memory) |
| JSON | `json_exporter.py` | pretty · compact · streaming NDJSON (orjson) |
| HTML | `html.py` | self-contained Jinja2 dashboard, inline CSS bar charts, theme-aware, email-safe |
| PDF | `pdf.py` | reportlab (lazy-imported `reports` extra): exec summary, stats, top matches, company bar chart, skill gap |

**Excel sheets**: Summary · Top Matches · All Jobs · Duplicate Jobs · Company
Statistics · Skill Gap Analysis · Collector Statistics · Pipeline Metrics ·
Search History.

### Notification architecture
`app/notifications/` — `smtp.SmtpNotifier` (implemented) sends multipart plain+HTML
email with attachments on a worker thread, with **retry (exponential backoff)**,
**rate limiting** (min interval), and **failure recovery** (final failure →
`NotificationError` → history marked failed). `channels.py` registers interface
**stubs** for Telegram / Slack / Discord / WhatsApp / Teams (same `Notifier` port,
`health_check → False`, `send → NotificationError`) so a new channel is a drop-in.
`service.NotificationService` generates the HTML body + attachments from one dataset
and delivers daily/weekly/monthly/custom reports.

### Analytics architecture
`app/analytics/service.py` — `AnalyticsService` loads stored jobs once and derives:
company / role / technology / skill / location / employment counts, salary
distributions (min/max/avg/median per currency+period), hiring trends (by day),
resume-match trends (per `resume_id`, score buckets), and pipeline performance
(from run history). Feeds both the reports and the `/analytics` API.

## Report history + versioning
`ReportRecord` (`report_history` collection) stores `report_id`, `run_id`,
`generated_at`, `format`, `recipient`, `delivery_status`, `file_location`,
`generation_time`, `download_count`, and the four version stamps. Every report
carries `report_version` / `schema_version` / `pipeline_version` /
`collector_versions`.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/reports`, `/reports/history` | report history (newest first) |
| GET | `/reports/{id}` | one report (counts as a download) |
| GET | `/analytics` | full analytics surface |
| GET | `/analytics/skills`·`/companies`·`/locations`·`/salaries`·`/trends` | slices |
| GET | `/exports` | supported formats |
| POST | `/exports/excel`·`/csv`·`/json`·`/html`·`/pdf` | generate a file |
| GET | `/notifications/channels` | channels (smtp + stubs) |
| POST | `/notifications/send` | generate + email a report |

## Performance (measured)

| Report | Target | Actual |
|---|---|---|
| Excel, 10,000 jobs | < 10 s | **7.5 s** |
| HTML dashboard | < 2 s | **0.04 s** |
| PDF | < 10 s | **0.55 s** |

## Dependency note
`jinja2` is a core dependency. `reportlab` (PDF) and `markdown` are the optional
`reports` extra, lazy-imported so the lean API image runs without them
(`PdfExporter.available()` reports installation; the Markdown renderer falls back
to a minimal converter).
