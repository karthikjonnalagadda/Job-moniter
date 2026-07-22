"""Base Pydantic models shared across domain and persistence layers.

Full domain schemas (Job, Company, Preferences, ...) are implemented in Phase 3.
Phase 2 provides only the reusable base + a Mongo ObjectId adapter so the app
imports cleanly and the API response envelope is available for /health.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Generic, TypeVar

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

T = TypeVar("T")


class _ObjectIdPydanticAnnotation:
    """Allow ``ObjectId`` to be used in Pydantic v2 models and serialised as str."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source: type[Any], _handler: Any
    ) -> core_schema.CoreSchema:
        def validate(value: Any) -> ObjectId:
            if isinstance(value, ObjectId):
                return value
            if isinstance(value, str) and ObjectId.is_valid(value):
                return ObjectId(value)
            raise ValueError("Invalid ObjectId")

        # Serialise to str only for JSON (API responses); keep a real ObjectId in
        # Python dumps so repositories persist native BSON ObjectIds to Mongo.
        return core_schema.no_info_plain_validator_function(
            validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                str, when_used="json"
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return handler(core_schema.str_schema())


PyObjectId = Annotated[ObjectId, _ObjectIdPydanticAnnotation]


class AppBaseModel(BaseModel):
    """Project-wide base: strict-ish, trims strings, enum values on dump."""

    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
        str_strip_whitespace=True,
        arbitrary_types_allowed=True,
        extra="ignore",
    )


class MongoDocument(AppBaseModel):
    """Base for documents persisted to MongoDB."""

    id: PyObjectId | None = Field(default=None, alias="_id")
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApiResponse(AppBaseModel, Generic[T]):
    """Uniform success envelope for API responses."""

    success: bool = True
    data: T | None = None
    message: str | None = None


class ApiError(AppBaseModel):
    """Uniform error body: ``{"error": {"code", "message", "details"}}``."""

    code: str
    message: str
    details: dict[str, Any] | None = None
