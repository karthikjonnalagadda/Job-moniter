# GitHub Source Report — Career-Page / Company-Seed Reference Investigation

**Date:** 2026-07-22
**Purpose:** Evaluate GitHub repositories and topics as **seed / reference leads** for building a company career-page database (India-focused). These are treated as *starting points for company names + official domains only* — NOT as authoritative or final data. No large verbatim datasets were copied; only company names and official domains were extracted as leads, and each was independently sanity-checked before inclusion in the seed file.

---

## Summary Judgement

| Source | Useful as seed? | Why |
|---|---|---|
| remoteintech/remote-jobs | Partial | Real structured company data (per-company markdown), but **global**, remote-tech focused, not India-specific. Good for a few global-with-India-office leads. |
| ever-jobs/ever-jobs | No (as data) | It is a **scraper/aggregator software tool**, not a dataset. Useful only as a reference for *which ATS endpoints exist*. |
| github/topics/greenhouse, /lever, /ats | No | Topics are dominated by application-autofill tools, resume parsers, and (for "greenhouse") literal greenhouse/gardening + Euro Truck Simulator repos. No company lists. |
| rshetye/AwesomeIndiaStartups | **Yes** | Large curated India **deeptech** list with official domains. Best single India seed source found. |
| ghoshsuman845/List-of-Top-Unicorn-Startups-India | Yes (names only) | Good India unicorn name list; no domains in repo (domains resolved independently). |
| softvar/awesome-startups (india.md) | Partial | India section exists but links point to startupranking.com profile pages, **not** official domains. Names usable; domains resolved independently. |
| harshamv/Bangalore-startups-companies-list, hemanth/bangalore-startups | Yes (names) | Bengaluru startup name lists; no reliable domains. |
| theainerd/MLInterview, chopwoodwater/MLKnowledge | Partial | AI-startup names embedded in an ML interview-prep repo; a few usable AI company leads. |
| Feashliaa/job-board-aggregator, adgramigna/job-board-scraper | No (as data) | ATS scrapers; illustrate feasibility of Greenhouse/Lever/Ashby crawling but ship no curated India company list. |

---

## Detailed Findings

### 1. https://github.com/remoteintech/remote-jobs
- **Contents:** Source for `remoteintech.company`, a community directory of remote-friendly tech companies. Each company is a structured markdown file at `src/companies/{slug}.md` with YAML frontmatter (name, website, region, etc.). Eleventy static-site generator.
- **Approx size:** ~40.6k stars, 3.9k forks, thousands of companies.
- **LICENSE:** ISC (permissive, similar to MIT).
- **India-specific?** No — global, remote-first tech companies. A handful have India presence but the list is not India-oriented.
- **Seed safety:** Safe as reference for *names + official website domains* (ISC permits reuse). Do not mirror the dataset wholesale; extract leads only.

### 2. https://github.com/ever-jobs/ever-jobs
- **Contents:** TypeScript/NestJS monorepo that aggregates job postings from 160+ sources (LinkedIn, Indeed, Greenhouse, Lever, Workday, company career sites) via REST/GraphQL/CLI/MCP. **It is software, not data** — no pre-scraped company dataset.
- **Approx size:** Active monorepo.
- **LICENSE:** MIT.
- **Seed safety:** Not a data source. Useful only to understand which ATS integrations are viable. Note: repo itself carries a scraping-ToS disclaimer.

### 3. GitHub Topics — /greenhouse, /lever, /ats, /ashby, /workday, /smartrecruiters
- **Contents:** Overwhelmingly *tooling*, not company lists:
  - `/greenhouse`: mostly application-autofillers, plus unrelated literal-greenhouse (gardening/IoT) repos.
  - `/lever`: resume parsers, autofill Chrome extensions, ATS adapter UIs (career-ops-ui, jobber, ai-job-agent).
  - `/ats`: OpenCATS (open-source ATS software), Resume-Matcher, career-ops, plus a cluster of Euro Truck Simulator "ATS" repos (name collision).
- **LICENSE:** Varies per repo (mostly MIT); not relevant since none provide company data.
- **Seed safety:** No usable structured company/careers data. Value is only conceptual (confirms Greenhouse/Lever/Ashby slug-based board URLs as crawl targets).

### 4. https://github.com/rshetye/AwesomeIndiaStartups  ★ best India source
- **Contents:** Curated markdown table of Indian **deeptech** startups (AI, robotics, IoT, cybersecurity, blockchain, quantum, healthtech) **with official website domains**.
- **Approx size:** Several hundred companies.
- **LICENSE:** BSD-3-Clause (permissive; attribution-style reuse OK).
- **India-specific?** Yes — explicitly India deeptech ecosystem.
- **Seed safety:** **Safe and high-value.** Extracted names + official domains (e.g., CynLr → cynlr.com, Addverb → addverb.com, CloudSEK → cloudsek.com, AccuKnox → accuknox.com, Dragonfruit AI → dragonfruit.ai, Qure.ai, Entropik). Each domain re-verified before use.

### 5. https://github.com/ghoshsuman845/List-of-Top-Unicorn-Startups-India
- **Contents:** README list of Indian unicorns grouped by sector (fintech, e-commerce, edtech, foodtech, logistics, healthtech). Names only — **no domains, no LICENSE file** visible.
- **Approx size:** ~100+ unicorn names.
- **Seed safety:** Safe for **names**; official domains resolved independently (all are well-known public companies: Paytm, PhonePe, Razorpay, Flipkart, Meesho, Swiggy, etc.).

### 6. https://github.com/softvar/awesome-startups → countries/india.md
- **Contents:** India section of a global awesome-startups list. ~100 India entries, but **hyperlinks point to startupranking.com profile pages, not official company domains.** Also somewhat dated (older cohort: Freshdesk, Zomato, Myntra, Practo, ClearTax, Exotel, LeadSquared...).
- **LICENSE:** Repo-level (typically MIT for awesome-lists); not load-bearing here.
- **Seed safety:** Names usable; **do not** use the startupranking.com URLs — resolve official domains separately (done).

### 7. Bangalore / AI name lists — harshamv/Bangalore-startups-companies-list, hemanth/bangalore-startups, theainerd/MLInterview, chopwoodwater/MLKnowledge
- **Contents:** Bengaluru startup name lists and AI-startup name mentions (Razorpay, BigBasket, ShareChat, Urban Ladder, Locus.sh, SigTuple, Niramai, etc.). Mostly names, few/no reliable official domains.
- **LICENSE:** MIT / unspecified per repo.
- **Seed safety:** Safe for **names**; domains resolved independently.

### 8. ATS scraper repos found via search — Feashliaa/job-board-aggregator, adgramigna/job-board-scraper
- **Contents:** Python ETL pipelines that crawl Greenhouse/Lever/Ashby/Workday board slugs (aggregator claims 20,000+ companies). **Software + live-scraped index, not a curated static company list.**
- **LICENSE:** MIT (typical); confirm per-repo before any code reuse.
- **Seed safety:** Not used as a data source. Confirms technical approach: enumerate ATS board slugs → resolve to companies. Any such crawling must respect each platform's ToS.

---

## Sourcing Rules Applied
- Extracted **company name + official domain only** — never job-portal URLs.
- Excluded LinkedIn, Naukri, Indeed, Glassdoor, Foundit, Wellfound, Instahyre, Apna, Cutshort, AngelList as domains.
- Where a repo linked to an aggregator profile (e.g., startupranking.com) instead of the official site, the official domain was resolved independently and the aggregator link discarded.
- Companies whose official domain could not be confidently confirmed were **omitted** rather than guessed.

## Recommended Seed Pipeline (for later phases)
1. Use `AwesomeIndiaStartups` (BSD-3) + unicorn list as the India name/domain backbone.
2. Enrich with GCC (Global Capability Center) rosters — global companies with major India engineering hubs (Microsoft, Google, Amazon, Adobe, Walmart Global Tech, Goldman Sachs, Target, etc.), using their **global official domains**.
3. For each confirmed domain, later resolve the actual ATS/careers endpoint (Greenhouse/Lever/Ashby/Workday slug or `/careers`) at crawl time — do NOT fabricate `/careers` paths at seed stage.
