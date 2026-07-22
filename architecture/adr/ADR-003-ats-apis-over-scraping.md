# ADR-003: Prefer ATS APIs over Web Scraping for Job Collection

- **Status:** Accepted
- **Date:** 2026-07-21
- **Deciders:** Project architecture team

## Context
Job postings must be collected reliably, daily, and at low maintenance cost from many companies. Most companies publish through a handful of ATS platforms — Greenhouse, Lever, Ashby, Workday — several of which expose documented public job-board JSON endpoints. The alternative, scraping rendered career pages, is brittle (breaks on any layout change), often requires headless browsers, and carries Terms-of-Service and legal risk. As a small team we cannot afford a maintenance treadmill of selector fixes, nor legal exposure.

## Decision
**Prefer documented ATS APIs and structured feeds over scraping.** Collectors follow a strict priority order: official career-page APIs/feeds → ATS job-board APIs → remote job boards → LinkedIn. A `legal_mode` flag (`api` | `feed` | `scrape`) is attached to every source and governs default enablement: `api`/`feed` sources are enabled by default; `scrape` sources are **opt-in only** and robots-aware. LinkedIn ships as a *registered-but-disabled* interface stub (`legal_mode=scrape`) that never runs by default, so the integration point exists without being exercised.

## Alternatives Considered
- **Pure scraping** — maximum source coverage, but brittle, browser-heavy, ToS-risky, and high-maintenance. Rejected as a default strategy.
- **Third-party aggregator APIs** — broad coverage in one integration, but recurring cost, data staleness, and their own ToS constraints; also hides provenance we want to control.
- **Hybrid with scraping as first-class** — rejected in favour of scraping only as an isolated, opt-in fallback.

## Trade-offs
We gain structured, stable, rate-limit-friendly JSON that survives page redesigns and keeps us on defensible legal footing. We give up coverage: only companies on supported ATS platforms are reachable via APIs, and some desirable sources are reachable only by scraping. Those remain available but quarantined behind opt-in `legal_mode=scrape`.

## Consequences
Positive: low-maintenance, resilient collectors; clean legal posture; provenance and rate limits under our control. Negative: source coverage is bounded by ATS adoption, and gaps must be filled deliberately. The `legal_mode` flag plus the collector registry make the enablement policy explicit and auditable; adding a compliant new source is a matter of registering an `api`/`feed` collector, while risky sources cannot slip into daily runs unnoticed.
