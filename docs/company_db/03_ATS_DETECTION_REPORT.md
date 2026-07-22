# ATS Detection & Coverage Report

ATS platform is detected from live page content + redirect URLs (single GET), with a generic-token guard to avoid false positives (e.g. shared CDN tokens). Detection method and a confidence score are stored per company.

## Detected ATS platforms (177 companies, 12.6% of DB)
| ATS | Companies | Collector status |
|---|---|---|
| workday | 69 | collector implemented |
| lever | 39 | collector implemented |
| successfactors | 20 | needs credentials (disabled) |
| greenhouse | 19 | collector implemented |
| oracle | 10 | needs credentials (disabled) |
| icims | 7 | needs credentials (disabled) |
| smartrecruiters | 4 | collector implemented |
| ashby | 4 | collector implemented |
| jazzhr | 3 | collector implemented |
| recruitee | 1 | collector implemented |
| teamtailor | 1 | collector implemented |

## Collector actionability
- **Immediately collectible now** (implemented + enabled collectors): **140** companies.
- **Needs credentials** (iCIMS / Oracle / SuccessFactors — collectors disabled): **37** companies.
- **ATS Unknown:** 1231 — mostly JS-rendered/custom career sites; not detectable via a single HTTP GET. A headless-browser detection pass is the recommended next step to raise coverage.

## Confidence & method
Each row carries `ats_confidence` (0.95 content-detected with token · 0.85 seeded · 0.75 platform-only) and `ats_detection_method` (`final_url` / `page_body` / `seed` / `none`).
