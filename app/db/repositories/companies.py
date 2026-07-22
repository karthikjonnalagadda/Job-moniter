"""Company repository.

Slug-keyed upsert (idempotent seed imports) plus lookups by ATS type and active
status used by the collection scheduler. Designed to scale to 10,000+ companies
via the indexes declared in ``app.db.indexes``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.db.repositories.base import MongoRepository
from app.models.company import Company
from app.models.enums import ATSType

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "companies"


class CompanyRepository(MongoRepository[Company]):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, COLLECTION, Company)

    async def get_by_slug(self, slug: str) -> Company | None:
        return await self.find_one({"slug": slug})

    async def upsert_by_slug(self, company: Company) -> Company:
        return await self.upsert({"slug": company.slug}, company)

    async def delete_by_slug(self, slug: str) -> bool:
        result = await self.collection.delete_one({"slug": slug})
        return result.deleted_count > 0

    async def list_by_ats(self, ats_type: ATSType, *, limit: int = 0) -> list[Company]:
        return await self.find({"ats_type": ats_type.value, "active_status": True}, limit=limit)

    async def list_active(self, *, limit: int = 0) -> list[Company]:
        return await self.find({"active_status": True}, limit=limit)

    async def mark_crawled(self, slug: str) -> Company | None:
        doc = await self.collection.find_one_and_update(
            {"slug": slug},
            {"$set": {"last_crawled": datetime.now(tz=UTC)}},
            return_document=True,
        )
        return self._to_model(doc)

    async def apply_ats_metadata(
        self,
        slug: str,
        *,
        ats_type: ATSType,
        ats_token: str | None = None,
        career_platform: str | None = None,
    ) -> Company | None:
        """Persist newly-discovered ATS wiring for a company (by slug)."""

        changes: dict[str, object] = {
            "ats_type": ats_type.value,
            "updated_at": datetime.now(tz=UTC),
        }
        if ats_token is not None:
            changes["ats_token"] = ats_token
        if career_platform is not None:
            changes["career_platform"] = career_platform
        doc = await self.collection.find_one_and_update(
            {"slug": slug}, {"$set": changes}, return_document=True
        )
        return self._to_model(doc)
