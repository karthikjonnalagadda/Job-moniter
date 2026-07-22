"""Production AI layer (Phase 8).

Swaps real semantic-retrieval implementations in behind the existing ports
(``EmbeddingProvider``, ``VectorScorer``, ``RankingEngine``) without changing any
business logic: model registry, embedding cache, resume/job embedding services,
vector search, AI metrics, and the explainability/skill-gap surface.
"""
