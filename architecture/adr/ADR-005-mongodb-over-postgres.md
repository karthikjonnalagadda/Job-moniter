# ADR-005: MongoDB Atlas over PostgreSQL as the Primary Datastore

- **Status:** Accepted
- **Date:** 2026-07-21
- **Deciders:** Project architecture team

## Context
The domain data is heterogeneous and fast-evolving. Every ATS source returns differently shaped job payloads; company-intelligence records carry deeply nested, variable sub-documents; resumes exist in multiple versions with differing fields; and we retain per-source raw payloads for provenance. On top of this, ranking needs 384-dim embeddings co-located with the documents they describe (see ADR-001), and the whole system runs async via Motor. Rigid, migration-heavy schemas would fight the natural shape and churn of this data.

## Decision
Use **MongoDB Atlas** as the primary datastore. The document model matches the semi-structured, per-source-varying nature of jobs and companies; schema can evolve without lock-step migrations; nested company-intelligence sub-documents are stored naturally; and Atlas Vector Search keeps embeddings on the same documents, avoiding a separate vector extension or service. Motor provides the async driver the rest of the stack expects.

## Alternatives Considered
- **PostgreSQL + pgvector** — excellent relational integrity, mature SQL, and JSONB for semi-structured fields. But fast-evolving, per-source-varying schemas mean frequent, rigid migrations, and vectors require a separate extension with its own operational surface. Strong, but a poorer fit for this data's churn.
- **SQLite** — trivial for a single user, but no vector search, no HA, and no path to scale. Rejected.

## Trade-offs
We gain schema flexibility, natural nesting, and co-located vectors with one operational store. We give up strong multi-document transactional guarantees, rich relational joins, and database-enforced integrity; we take on eventual-consistency considerations and the burden of enforcing schema discipline *in the application* rather than the database.

## Consequences
Positive: the datastore bends with the domain instead of resisting it, and vector search needs no extra service. Negative: without a schema engine, uncontrolled documents could rot. Mitigations: Pydantic v2 models enforce schema at the application boundary; indexes plus a unique job-hash prevent duplicates; and repositories centralise access. If strong relational integrity or heavy analytical reporting needs later emerge, a dedicated read-model or warehouse can be layered on without disturbing the operational document store.
