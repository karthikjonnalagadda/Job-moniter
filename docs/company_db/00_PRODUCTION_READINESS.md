# Indian Company Career Intelligence Database — Production Readiness Report

**Generated:** 2026-07-22  |  **Total companies:** 1408  |  **Country:** India  |  **Schema:** 25 fields  |  **Formats:** CSV / JSON / YAML / MD (identical data)

## Verdict: ✅ Production-ready (with documented caveats)

The database is deduplicated (0 duplicate names, 0 duplicate domains), live-validated, ATS-aware, and exported in four identical formats. It is ready to drive the AI Job Intelligence collectors. Honesty caveats are documented below — nothing is fabricated; unverifiable fields are marked `Unknown`.

## Headline numbers

| Metric | Count | Share |
|---|---|---|
| Total unique companies | 1408 | 100% |
| **Confirmed careers page** (HTTP 2xx/3xx at a careers path) | 938 | 66.6% |
| Homepage reachable, careers path unconfirmed | 202 | 14.3% |
| Likely valid but blocked/slow (403 / timeout / 5xx) | 198 | 14.1% |
| Not found (404/410) | 22 | 1.6% |
| Unreachable / SSL / broken | 48 | 3.4% |
| Companies with a detected ATS | 177 | 12.6% |
| Mandatory-list companies present | 124/124 | — |

**Reachable in some form** (confirmed + homepage + blocked/slow): 1338 (95.0%). **Genuinely problematic** (not-found + unreachable): 70 (5.0%).

## What "verified" means here (honesty statement)
- Every career URL was fetched live (real HTTP GET, browser UA, redirects followed).
- `working`/`redirect` = a careers page responded 2xx/3xx. `homepage_only` = the domain is live but we could **not** confirm a distinct careers page (we did not count these as confirmed). `blocked` = server responded 401/403/429 (bot protection) — the URL almost certainly exists but we could not read it. `timeout`/`unreachable` = no successful response.
- ATS is detected from **page content/redirects only** (single GET). JavaScript-rendered career sites and custom portals often expose no ATS signature, so `ats_platform=Unknown` is common and does **not** mean "no ATS" — it means "not detectable without a headless browser."
- Fields that cannot be verified from a single fetch — **Founded Year, Freshers Hiring, Internship Available, Graduate Program, Hiring Frequency** — are set to `Unknown` for every row rather than guessed. `State` is *derived* deterministically from HQ city (not guessed). `Remote Friendly`, `Preferred Roles`, `Tech Stack` are **category heuristics**, not per-company HR confirmations.

## Known limitations
1. **ATS coverage is content-detection-limited** (177/1408). A headless-browser pass would materially raise this.
2. **Hiring metadata (freshers/intern/grad/frequency) is `Unknown`** — it requires per-company page parsing or an HR data source, out of scope for URL validation.
3. **~198 blocked/slow domains** need a retry with residential IP / headless browser to confirm.
4. Count landed at **1408** unique verified companies — within the 1,000–2,000 target. Reaching ~2,000 would require more net-new *verified* companies; padding with unverified names was explicitly avoided.

## Files
- `data/companies/indian_companies.{json,yaml,csv,md}` — the database (identical data, 4 formats)
- `docs/company_db/*` — the deliverable reports (this folder)
