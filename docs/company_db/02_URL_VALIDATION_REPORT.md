# URL Validation Report

Every `career_url` was fetched live (HTTP GET, Chrome UA, follow redirects, 12s timeout). Failing careers paths were retried against standard alternates on the **same official domain** (careers./jobs. subdomains, /careers, /jobs, /company/careers, …). 

## Status breakdown
| Status | Count | Share |
|---|---|---|
| working | 548 | 38.9% |
| redirect | 390 | 27.7% |
| homepage_only | 202 | 14.3% |
| blocked | 111 | 7.9% |
| timeout | 77 | 5.5% |
| unreachable | 45 | 3.2% |
| not_found | 22 | 1.6% |
| server_error | 10 | 0.7% |
| broken | 3 | 0.2% |

### Status definitions
- **working** — careers page returned 2xx at the requested path.
- **redirect** — returned 2xx after redirect (final URL differs).
- **homepage_only** — resolved to the bare corporate root with no careers path and no ATS; domain live but careers page **unconfirmed**.
- **blocked** — 401/403/429 (bot protection / WAF); URL likely valid, content unread.
- **timeout / server_error** — no successful response (slow host or 5xx); likely transient.
- **not_found** — 404/410 after alternate-path recovery failed.
- **unreachable / ssl_error / broken** — DNS/connection/TLS failure.

## Summary
- **Confirmed careers page:** 938 (66.6%)
- **Domain live (confirmed + homepage_only):** 1140 (81.0%)
- **Reachable in some form:** 1338 (95.0%)
- **Genuinely problematic (not-found + unreachable):** 70 (5.0%)

No career URL points to LinkedIn, Naukri, Indeed, Glassdoor, Foundit, Wellfound, Instahyre, Apna, Cutshort, or AngelList — official domains only.
