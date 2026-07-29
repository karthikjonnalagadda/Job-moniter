# ATS & Job-Board API Research

_Verified live on 2026-07-30 with `scripts/verify_ats_tokens.py` against the real
endpoints. This documents how each source works, how to find a correct token, and
what is / isn't fetchable._

## TL;DR

- Of **1,408** seeded companies, only **24** currently return live jobs. Breakdown:
  | status | count | meaning |
  |---|---|---|
  | `NO_ATS` | 1,249 | no `ats_token` at all → uncollectable via any API |
  | `NEEDS_CONFIG` | 88 | Workday/Oracle/SuccessFactors/iCIMS — token alone insufficient |
  | `HTTP_ERR` (mostly 404) | 43 | wrong token — company isn't on that ATS |
  | `NEEDS_AUTH` | 4 | Teamtailor/JazzHR/BambooHR — need an API key |
  | **`OK`** | **24** | **working boards** |
- **The bottleneck is data quality, not the pipeline.** Fixing Workday (+88) and
  adding aggregator APIs (below) is where the coverage gains are.
- **LinkedIn and Naukri have no usable public API.** Get their listings *indirectly*
  through licensed aggregators (Adzuna, Jooble, JSearch) — details at the bottom.

---

## 1. The clean ATS APIs (no auth, work today)

### Greenhouse ✅ best signal
```
GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
```
- `token` = the board slug in `boards.greenhouse.io/{token}` or `job-boards.greenhouse.io/{token}`.
- Public, no key. `200` with `{"jobs":[...], "meta":{...}}`; `404` if the token isn't a real board.
- Per-job detail: `.../boards/{token}/jobs/{id}` returns full HTML description.
- **How to find the token:** open the company careers page; if "Apply" links go to
  `boards.greenhouse.io/acme`, the token is `acme`. Verified working: `figma`,
  `postman`, `turing`, `druva`, `observeai`, `zenoti`, `nanonets`, `karya`, `glance`.

### Lever ✅
```
GET https://api.lever.co/v0/postings/{token}?mode=json&limit=100&offset=0
```
- `token` = slug in `jobs.lever.co/{token}`.
- Public, no key. Returns a JSON array of postings; paginate with `offset`.
- `404` if the company isn't a Lever customer (that's why `razorpay`, `groww`,
  `zepto`, `swiggy`… failed — they simply aren't on Lever).
- Verified working: `paytm`, `cred`, `meesho`, `zeta`, `epifi`, `porter`,
  `mindtickle`, `100ms`, `hevodata`, `levelai`, `safe`.

### SmartRecruiters ✅
```
GET https://api.smartrecruiters.com/v1/companies/{companyId}/postings?limit=100&offset=0
```
- `companyId` = the company's SmartRecruiters identifier (e.g. `Freshworks`,
  `BoschGroup`, `TheNielsenCompany`), case-sensitive.
- Public postings API, no key. Response has `content[]` + `totalFound`.
- Verified working: `BoschGroup` (4,743 postings!), `Freshworks`, `TheNielsenCompany`, `AbhiBus`.

### Ashby ⚠️ needs the org to enable the public API
```
POST https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true
```
- `token` = slug in `jobs.ashbyhq.com/{token}`.
- Returns `401` unless the organization has switched the public Job Posting API on.
  Many Ashby customers (e.g. `sarvam`) leave it off → not fetchable. Not a bug.

### Recruitee ✅
```
GET https://{token}.recruitee.com/api/offers/
```
- `token` = the company's Recruitee subdomain. Public JSON (`offers[]`).

---

## 2. Workday — the big missed bucket (88 companies) ⚠️

Workday is the single largest ATS in the seed list, and **every one currently fails**
because a token isn't enough. The real endpoint is:
```
POST https://{host}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
Body: {"appliedFacets":{}, "limit":20, "offset":0, "searchText":""}
```
You need three values, all visible in the public careers URL:
```
https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite
         └host┘ └N┘                  └tenant┘ └────site─────────┘
→ host=nvidia, N=5, tenant=nvidia, site=NVIDIAExternalCareerSite
```
The collector already supports this (it errored `requires extra.host, extra.tenant
and extra.site`) — the seed CSV just never captured those fields. **Action:** add
`wd_host`, `wd_tenant`, `wd_site` columns for the 88 Workday companies (or drop them).
This is the highest-value coverage fix available.

---

## 3. Verifying & pruning the registry

`scripts/verify_ats_tokens.py` probes every company against its real endpoint:
```bash
python -m scripts.verify_ats_tokens                # report only
python -m scripts.verify_ats_tokens --write-clean  # also emit indian_companies.clean.csv
```
- `indian_companies.verified.csv` — every row annotated with `probe_status` + `job_count`.
- `indian_companies.clean.csv` — only boards that returned ≥1 live posting (the 24).

Run it periodically; boards come and go. Wire the pipeline to the clean list (or import
only `probe_status == OK` rows into Mongo) so the daily run stops wasting its budget on
404s.

---

## 4. LinkedIn & Naukri — can we fetch them?

**Short answer: not through any official/free API, and direct scraping is against their
ToS and actively blocked. Don't build on it.**

| Platform | Official API? | Reality |
|---|---|---|
| **LinkedIn** | Only partner "Talent Solutions / Job Posting" APIs — for *posting* jobs, gated behind a signed partnership. No public job-*search* API. | Scraping violates the User Agreement, is behind auth/rate walls, and has hostile legal history (hiQ v. LinkedIn). Accounts get banned. |
| **Naukri** | None public. | Bot-protected; ToS forbids scraping. Same risk profile. |

### The right way to get LinkedIn/Naukri-listed jobs: licensed aggregators
These have **real APIs** and legally re-list postings from LinkedIn/Naukri/Indeed/etc.,
so you get the same jobs without the ToS/ban risk:

| Provider | API | Free tier | India coverage | Notes |
|---|---|---|---|---|
| **Adzuna** | `api.adzuna.com` | Yes (app_id+key) | Good (`/v1/api/jobs/in/search`) | Clean JSON, salary data. Best first add. |
| **Jooble** | `jooble.org/api` | Yes (key on request) | Good | Aggregates many boards incl. LinkedIn-sourced. |
| **JSearch** (RapidAPI) | RapidAPI | Freemium | Global incl. India | Wraps Google-for-Jobs → surfaces LinkedIn/Indeed postings. |
| **Careerjet** | affiliate API | Yes | Good | Aggregator, India locale. |
| **Remotive / RemoteOK / Arbeitnow** | public JSON | Yes | Remote-focused | Already partly wired (`remoteok`, etc.). |

**Recommendation:** add an **Adzuna** collector first (free, clean, India-native,
returns salary), then **JSearch** if you specifically want LinkedIn-origin postings.
Both fit the existing collector interface and stay fully within ToS. This gets you the
breadth you were hoping LinkedIn/Naukri would provide.
```
GET https://api.adzuna.com/v1/api/jobs/in/search/1
    ?app_id={id}&app_key={key}&results_per_page=50
    &what=python%20developer&where=Bengaluru&max_days_old=1
```
