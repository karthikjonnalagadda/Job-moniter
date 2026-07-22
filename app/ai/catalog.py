"""Static catalog of supported embedding models.

The registry (runtime state) and providers read model *specs* from here so that
switching ``BAAI/bge-small-en-v1.5`` for ``bge-base``/``e5-base-v2``/
``all-MiniLM-L6-v2`` is pure configuration — no code change, exactly as the
approved architecture requires. Unknown models are still usable: ``spec_for``
synthesises a spec from the configured vector dimensions.
"""

from __future__ import annotations

from app.models.base import AppBaseModel

# bge models want an instruction prefix on the *query* side only. e5 models use
# "query:" / "passage:" prefixes; MiniLM needs none. Encapsulated here so the
# provider stays model-agnostic.
_BGE_QUERY = "Represent this resume for retrieving relevant job descriptions: "
_E5_QUERY = "query: "


class ModelSpec(AppBaseModel):
    """Immutable description of a supported embedding model."""

    name: str
    dimensions: int
    max_seq_length: int = 512
    query_instruction: str = ""
    document_instruction: str = ""
    description: str = ""
    license: str = "unknown"


#: Supported models. Extend this list to add a model — no other code changes.
CATALOG: dict[str, ModelSpec] = {
    "BAAI/bge-small-en-v1.5": ModelSpec(
        name="BAAI/bge-small-en-v1.5",
        dimensions=384,
        max_seq_length=512,
        query_instruction=_BGE_QUERY,
        description="Default production encoder — small, fast, strong retrieval.",
        license="MIT",
    ),
    "BAAI/bge-base-en-v1.5": ModelSpec(
        name="BAAI/bge-base-en-v1.5",
        dimensions=768,
        max_seq_length=512,
        query_instruction=_BGE_QUERY,
        description="Higher-capacity bge; better recall at 2x the dimensions.",
        license="MIT",
    ),
    "intfloat/e5-base-v2": ModelSpec(
        name="intfloat/e5-base-v2",
        dimensions=768,
        max_seq_length=512,
        query_instruction=_E5_QUERY,
        document_instruction="passage: ",
        description="E5 base — asymmetric query/passage prefixes.",
        license="MIT",
    ),
    "sentence-transformers/all-MiniLM-L6-v2": ModelSpec(
        name="sentence-transformers/all-MiniLM-L6-v2",
        dimensions=384,
        max_seq_length=256,
        query_instruction="",
        description="MiniLM — tiny, ubiquitous baseline, no instruction prefix.",
        license="Apache-2.0",
    ),
}


def spec_for(model_name: str, *, default_dimensions: int = 384) -> ModelSpec:
    """Return the catalog spec for ``model_name``, or a synthesised default.

    Keeps unknown/custom models first-class: they run with the configured vector
    dimensions and no instruction prefix.
    """

    known = CATALOG.get(model_name)
    if known is not None:
        return known
    return ModelSpec(
        name=model_name,
        dimensions=default_dimensions,
        description="Custom model (not in catalog) — using configured dimensions.",
    )


def known_models() -> list[ModelSpec]:
    """All catalogued model specs (stable order)."""

    return list(CATALOG.values())
