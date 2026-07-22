# ADR-002: Clean Architecture with Hexagonal Ports & Adapters

- **Status:** Accepted
- **Date:** 2026-07-21
- **Deciders:** Project architecture team

## Context
The AI Job Intelligence Agent is a long-lived platform with an ambitious roadmap: many planned modules (cover letters, application tracking, analytics, extra notification channels, dashboards) and a plugin-based collector system that must absorb new job sources without destabilising existing behaviour. The system touches many volatile external concerns — MongoDB, HTTP collectors against half a dozen ATS platforms, SMTP email, ML embeddings, a vector search engine, caching, and metrics. If these leak into business logic, every infrastructure change becomes a domain change, and testing requires live services.

## Decision
Adopt **Clean Architecture combined with Hexagonal (Ports & Adapters)**. The domain (`app/core`) stays pure and dependency-free — no imports of Motor, FastAPI, `requests`, or `torch`. Every external concern is expressed as a *port* (an abstract interface) with one or more swappable *adapters*: `BaseCollector` for sources, repository ports for persistence, `Notifier` for delivery, `EmbeddingProvider`, `VectorScorer`, `Exporter`, cache, and metrics. Dependencies point inward only (Dependency Inversion); orchestration lives in `app/services/`.

## Alternatives Considered
- **Layered / N-tier** — familiar, but data-access and framework types routinely leak upward into the domain, eroding testability over time.
- **Transaction-script / anemic domain** — quick for small apps, but the planned module count would turn services into a tangle of procedural glue with no reusable domain.
- **Framework-centric (FastAPI-coupled) design** — fast to bootstrap, but binds business rules to request/response objects and the web framework, making batch jobs and alternative channels awkward.

## Trade-offs
We accept more upfront indirection: interface definitions, adapter wiring, and some boilerplate that a smaller app would not need. Interface proliferation and a steeper onboarding curve are real costs. In return we get a domain that is trivially unit-testable with fakes and `mongomock`, infrastructure that swaps without touching business rules, and a plugin system that extends by adding adapters rather than editing the core.

## Consequences
Positive: high testability, clean seams for the collector registry and future modules, and enforced SOLID/DIP discipline. Negative: navigating the codebase means following ports to adapters, and trivial features still pay the interface tax. Given the project's expected lifetime and module count, the indirection is a deliberate, justified investment rather than accidental complexity.
