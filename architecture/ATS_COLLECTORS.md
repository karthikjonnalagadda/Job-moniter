# ATS Collectors & Company Data Pipeline (Phase 5)

This document is the operator reference for the 15 production ATS collectors and
the Indian company career-site dataset pipeline delivered in Phase 5. It
complements [EXTENSIBILITY.md](EXTENSIBILITY.md) and
[ADR-003](adr/ADR-003-ats-apis-over-scraping.md) (documented APIs over scraping).

## Supported ATS matrix

All collectors extend `BaseATSCollector` and are auto-discovered from
`app/collectors/ats/`. Enablement/priority come from `data/ats_sources.yaml`
(nothing hardcoded). "Auth" = requires per-target credentials in `target.extra`.

| Pri | Collector       | Upstream API                                   | Enabled | Pagination | Incremental | Auth |
|-----|-----------------|------------------------------------------------|---------|------------|-------------|------|
| 2   | greenhouse      | Job Board API (`boards-api.greenhouse.io`)     | ✅      | –          | ETag/304    | –    |
| 3   | lever           | Postings v0 (`api.lever.co`)                   | ✅      | offset     | –           | –    |
| 4   | ashby           | Posting API (`api.ashbyhq.com`, POST)          | ✅      | –          | –           | –    |
| 5   | workday         | CXS (`{host}/wday/cxs/{tenant}/{site}/jobs`)   | ✅      | offset     | –           | host/site |
| 6   | smartrecruiters | Posting API v1 (`api.smartrecruiters.com`)     | ✅      | offset     | –           | –    |
| 7   | bamboohr        | Careers list (`{sub}.bamboohr.com/careers`)    | ✅      | –          | –           | –    |
| 8   | teamtailor      | JSON:API v1 (`api.teamtailor.com`)             | ✅      | page       | –           | api_key |
| 9   | recruitee       | Offers (`{sub}.recruitee.com/api/offers`)      | ✅      | –          | –           | –    |
| 10  | jobvite         | Job v2 (`api.jobvite.com`)                     | ✅      | page       | –           | api+sc |
| 11  | icims           | Customer Search (`api.icims.com`)              | ⛔      | –          | –           | bearer |
| 12  | oracle          | Recruiting CE REST (`{host}/hcmRestApi`)       | ⛔      | offset     | –           | host/site |
| 13  | successfactors  | Recruiting OData v2 (`{host}/odata/v2`)        | ⛔      | `$skip`    | –           | basic |
| 14  | comeet          | Careers API v2 (`comeet.co/careers-api`)       | ✅      | –          | –           | token |
| 15  | breezyhr        | JSON board (`{sub}.breezy.hr/json`)            | ✅      | –          | –           | –    |
| 16  | jazzhr          | Resumator v1 (`api.resumatorapi.com`)          | ✅      | –          | –           | api_key |

`icims`, `oracle`, and `successfactors` are **registered but disabled by
default**: they are enterprise ATSes with no anonymous board feed, so they only
run when an operator both enables them in `ats_sources.yaml` and supplies the
per-target credentials/host documented in each module's docstring.

### What each collector implements (Phase-5 contract)

Every collector inherits from `BaseATSCollector`, so all of them: use the shared
`HttpClient` (circuit breaker + per-host rate limiting); archive raw payloads
when `JOBAGENT_COLLECTOR__ARCHIVE_RAW=true`; normalise source rows into the
common `RawJob` and `validate()` before emitting; expose the four health probes;
capture the incremental sync watermark; and — via `CollectorExecutor` — fail
independently under bulkhead isolation, record benchmarks, and enqueue retries.
A new ATS is still just `_collect` + `_to_raw_job`.

## Career-site routing

`CompanyRouter` maps each company to exactly one source (no duplicate
collection), preferring an ATS collector over the generic career crawler:

1. **Detect** — `ATSDetector` (`app/routing/detector.py`) infers `ats_type` /
   `ats_token` / `career_platform` from the career URL (pattern-based, no
   network). E.g. `jobs.lever.co/acme → (lever, acme)`.
2. **Prefer ATS** — if the company has an ATS and its source is enabled, route
   there.
3. **Fall back** — otherwise route to the `career_site` collector.
4. **De-dupe** — a company yields one routing decision, never two.
5. **Continuously enrich** — `ATSMetadataUpdater` (`app/routing/ats_updater.py`)
   re-detects and **persists** ATS wiring for companies whose ATS is still
   `unknown`, conservatively (never overwrites a set ATS, only writes above a
   confidence threshold). Wired into `POST /companies/sync` (default `enrich=true`),
   `POST /companies/enrich-ats`, and the `job-agent-sync` CLI.

## Indian company career-site dataset

Pipeline (`app/importers/india_seed.py`, CLI `job-agent-build-india`):

```
Indian_Company_Career_Sites.md (seed table) ─┐
                                             ├─ merge by slug ─ ATS auto-detect ─┬─ CSV
indian_company_metadata.yaml (curated 200+) ─┘                                   ├─ JSON
                                                                                 ├─ YAML
                                                                                 └─ Mongo (via CompanyImportService)
```

* The seed list is parsed by `parse_seed_table` (tolerant of the Pandoc grid
  layout and plain Markdown pipe tables).
* The curated metadata file expands coverage across all requested categories
  (IT services, product, SaaS, fintech, edtech, healthtech, e-commerce,
  analytics/AI, consulting, BFSI, manufacturing, automotive, telecom, energy,
  retail, pharma, conglomerates, unicorns, startups).
* Records carry the full company schema: name, slug, career URL, career
  platform, industry, HQ, country, company category, ATS type + token, priority
  score, AI-hiring score, remote support, active status, crawl frequency,
  supported roles, preferred technologies, aliases, notes.
* One validation/upsert path: all four output formats flow through the existing
  `CompanyValidator` + `CompanyImportService` (dedup, dry-run, rollback,
  dead-letter, import history). Designed to scale to 10,000+ rows (streaming CSV,
  flat records, O(1) slug upserts).

Regenerate with:

```bash
job-agent-build-india                 # writes CSV/JSON/YAML to data/companies/
job-agent-build-india --import        # + upsert into MongoDB
job-agent-build-india --import --dry-run
```
