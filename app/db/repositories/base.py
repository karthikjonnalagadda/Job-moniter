"""Generic async repository (Repository Pattern over MongoDB/Motor).

``Repository`` is the port; ``MongoRepository`` is the Motor-backed adapter that
handles the Pydantic<->BSON round-trip, ``_id``/``ObjectId`` handling, and
``created_at``/``updated_at`` stamping once, so concrete repositories only add
domain queries. Services depend on the abstract ``Repository`` (or a concrete
subclass), never on Motor directly — which isolates persistence and keeps the
domain testable with an in-memory Mongo mock.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from bson import ObjectId

from app.core.exceptions import NotFoundError
from app.models.base import MongoDocument

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

T = TypeVar("T", bound=MongoDocument)

Sort = list[tuple[str, int]]


class Repository(ABC, Generic[T]):
    """Abstract typed CRUD contract for an aggregate of type ``T``."""

    @abstractmethod
    async def insert(self, entity: T) -> T: ...

    @abstractmethod
    async def get(self, entity_id: str | ObjectId) -> T | None: ...

    @abstractmethod
    async def find_one(self, filter: dict[str, Any]) -> T | None: ...

    @abstractmethod
    async def find(
        self,
        filter: dict[str, Any] | None = None,
        *,
        limit: int = 0,
        skip: int = 0,
        sort: Sort | None = None,
    ) -> list[T]: ...

    @abstractmethod
    async def update(self, entity_id: str | ObjectId, changes: dict[str, Any]) -> T | None: ...

    @abstractmethod
    async def upsert(self, filter: dict[str, Any], entity: T) -> T: ...

    @abstractmethod
    async def delete(self, entity_id: str | ObjectId) -> bool: ...

    @abstractmethod
    async def count(self, filter: dict[str, Any] | None = None) -> int: ...


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _as_object_id(value: str | ObjectId) -> ObjectId:
    return value if isinstance(value, ObjectId) else ObjectId(value)


class MongoRepository(Repository[T]):
    """Motor-backed generic repository."""

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        collection_name: str,
        model: type[T],
    ) -> None:
        self._collection: AsyncIOMotorCollection = db[collection_name]
        self._model = model
        self._collection_name = collection_name

    @property
    def collection(self) -> AsyncIOMotorCollection:
        return self._collection

    # ---- serialization helpers ------------------------------------------
    def _to_doc(self, entity: T) -> dict[str, Any]:
        # mode="python" preserves ObjectId/datetime for BSON (see models.base).
        doc = entity.model_dump(by_alias=True, mode="python")
        if doc.get("_id") is None:
            doc.pop("_id", None)
        return doc

    def _to_model(self, doc: dict[str, Any] | None) -> T | None:
        return self._model.model_validate(doc) if doc is not None else None

    # ---- CRUD -----------------------------------------------------------
    async def insert(self, entity: T) -> T:
        doc = self._to_doc(entity)
        now = _now()
        if doc.get("created_at") is None:
            doc["created_at"] = now
        doc["updated_at"] = now
        result = await self._collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return self._model.model_validate(doc)

    async def get(self, entity_id: str | ObjectId) -> T | None:
        doc = await self._collection.find_one({"_id": _as_object_id(entity_id)})
        return self._to_model(doc)

    async def get_or_404(self, entity_id: str | ObjectId) -> T:
        entity = await self.get(entity_id)
        if entity is None:
            raise NotFoundError(f"{self._collection_name} '{entity_id}' not found")
        return entity

    async def find_one(self, filter: dict[str, Any]) -> T | None:
        return self._to_model(await self._collection.find_one(filter))

    async def find(
        self,
        filter: dict[str, Any] | None = None,
        *,
        limit: int = 0,
        skip: int = 0,
        sort: Sort | None = None,
    ) -> list[T]:
        cursor = self._collection.find(filter or {})
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        docs = await cursor.to_list(length=limit or None)
        return [m for doc in docs if (m := self._to_model(doc)) is not None]

    async def update(self, entity_id: str | ObjectId, changes: dict[str, Any]) -> T | None:
        changes = {**changes, "updated_at": _now()}
        doc = await self._collection.find_one_and_update(
            {"_id": _as_object_id(entity_id)},
            {"$set": changes},
            return_document=True,
        )
        return self._to_model(doc)

    async def upsert(self, filter: dict[str, Any], entity: T) -> T:
        doc = self._to_doc(entity)
        doc.pop("_id", None)
        # created_at is owned by $setOnInsert; keep it out of $set to avoid a
        # MongoDB path conflict between the two operators.
        doc.pop("created_at", None)
        now = _now()
        doc["updated_at"] = now
        result = await self._collection.find_one_and_update(
            filter,
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
            return_document=True,
        )
        return self._model.model_validate(result)

    async def delete(self, entity_id: str | ObjectId) -> bool:
        result = await self._collection.delete_one({"_id": _as_object_id(entity_id)})
        return result.deleted_count > 0

    async def count(self, filter: dict[str, Any] | None = None) -> int:
        return await self._collection.count_documents(filter or {})
