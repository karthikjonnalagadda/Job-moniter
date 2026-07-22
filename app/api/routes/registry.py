"""Source registry endpoints.

* ``GET /registry``       — all source definitions (priority-ordered).
* ``GET /registry/stats`` — aggregate counts by type / legal mode / enablement.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_source_registry
from app.registry.models import SourceDefinition, SourceRegistryStats
from app.registry.service import SourceRegistry

router = APIRouter(tags=["registry"])

RegistryDep = Annotated[SourceRegistry, Depends(get_source_registry)]


@router.get("", response_model=list[SourceDefinition])
async def list_sources(registry: RegistryDep) -> list[SourceDefinition]:
    return registry.by_priority()


@router.get("/stats", response_model=SourceRegistryStats)
async def registry_stats(registry: RegistryDep) -> SourceRegistryStats:
    return registry.stats()
