from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, ValidationError


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class MongoDocument(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

    id: str | None = Field(default=None, alias="_id")
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

    @classmethod
    def from_mongo(cls, data: dict[str, Any] | None):
        if data is None:
            return None
        data = dict(data)
        if "_id" in data and isinstance(data["_id"], ObjectId):
            data["_id"] = str(data["_id"])
        try:
            return cls.model_validate(data)
        except ValidationError:
            return None

    def to_mongo(self) -> dict[str, Any]:
        data = self.model_dump(by_alias=True, exclude_none=True)
        if "_id" in data and isinstance(data["_id"], str) and ObjectId.is_valid(data["_id"]):
            data["_id"] = ObjectId(data["_id"])
        return data
