# Contributing

Thanks for your interest in improving the AI Job Intelligence Agent. This guide
covers the development workflow, coding standards, and PR process.

## Ground rules

- Be respectful — see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- **Never commit secrets or personal data.** No `.env`, credentials, resumes,
  connection strings, or API tokens. See [SECURITY.md](SECURITY.md).
- Discuss significant changes in an issue before opening a large PR.

## Development setup

```bash
git clone https://github.com/karthikjonnalagadda/Job-moniter.git
cd Job-moniter
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env               # fill in local values
```

For work touching embeddings/ranking, also install the ML extra:

```bash
pip install -e ".[ml]"
```

## Quality gates (run before every commit)

```bash
ruff check app tests    # lint (and: ruff check --fix for autofixes)
mypy app                # type-check
pytest                  # full suite
```

All three must pass. CI (`.github/workflows/ci.yml`) enforces the same gates on
every push and pull request.

## Coding standards

- **Architecture:** Clean / Hexagonal. Keep the domain (`app/core`) free of I/O.
  External concerns (Mongo, HTTP, SMTP, embeddings) live behind ports with
  swappable adapters.
- **Principles:** SOLID, DRY, KISS. Prefer composition and dependency injection
  (see `app/api/deps.py`).
- **Async-first:** I/O is `async`; repositories use Motor.
- **Typing:** full type hints; `disallow_untyped_defs` is on. No new `# type:
  ignore` without justification.
- **Style:** ruff-formatted, line length 100. Match the surrounding code.
- **Tests:** add/adjust unit or integration tests for every behavior change.
  Tests must not require network, real credentials, or personal data.

## Commit & PR process

1. Branch from `main`: `git checkout -b feature/short-description`.
2. Make focused commits with clear messages (imperative mood).
3. Ensure the quality gates pass locally.
4. Open a PR describing **what** changed and **why**; link related issues.
5. Keep PRs small and reviewable.

## Adding a new collector

New ATS/career-site collectors subclass `BaseCollector` in `app/collectors/`,
register capability metadata, and only ever read from **official sources or
documented ATS APIs** — never job-board aggregators. Add a unit test covering
parsing of a representative payload.
