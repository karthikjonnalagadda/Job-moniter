# ADR-001: MongoDB Atlas Vector Search over FAISS for Semantic Job Ranking

- **Status:** Accepted
- **Date:** 2026-07-21
- **Deciders:** Project architecture team

## Context
The platform ranks fresh job postings against a user's resume using 384-dimensional embeddings (`BAAI/bge-small-en-v1.5`). Ranking must combine semantic similarity with structured metadata pre-filters (`status`, `work_mode`, `location`, freshness) and operate over a corpus that is small-to-modest but *frequently updated* — new postings arrive daily, stale ones are pruned. The system already stores every job and company document in MongoDB Atlas, runs on a daily GitHub Actions batch, and is maintained by a very small team (effectively a single maintainer). Operational simplicity and low fixed cost matter more than squeezing out microseconds of ANN latency.

## Decision
Use **MongoDB Atlas Vector Search** (`$vectorSearch`) as the production similarity engine. Embeddings are stored on the same job documents they describe, so a single aggregation query performs approximate-nearest-neighbour search *and* metadata pre-filtering with no cross-store synchronisation. A `VectorScorer` interface abstracts the operation; a NumPy cosine-similarity implementation sits behind the same interface for local development, unit tests, and offline runs.

## Alternatives Considered
- **FAISS** — extremely fast, in-process ANN. But it offers no persistence, no metadata filtering, and no HA; the index must be rebuilt and co-deployed with the app, which is a poor fit for a corpus that changes daily. Rejected as primary.
- **pgvector (Postgres)** — solid and cheap, but would require introducing and operating a relational store solely for vectors while our documents live in Mongo (see ADR-005).
- **Pinecone / Weaviate / Qdrant** — capable managed vector DBs, but each adds a *second* managed service, a second SLA, extra cost, and a sync pipeline between it and Mongo.

## Trade-offs
We gain a single source of truth, transactional co-location of data and vectors, managed replication, and one query for filter-plus-search. We give up FAISS-grade raw ANN tuning, accept vendor coupling to Atlas, and require at least the M10+ tier (a real recurring cost versus a free in-process library).

## Consequences
Positive: no separate index infrastructure to operate or keep consistent; filters and search stay atomic; scaling is Atlas's problem. Negative: cost floor and Atlas lock-in. Mitigation: the `VectorScorer` port keeps the domain independent of Atlas — the NumPy scorer proves the abstraction and provides an escape hatch if we ever need to migrate or self-host.
