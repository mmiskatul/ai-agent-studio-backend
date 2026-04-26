from abc import ABC
from logging import getLogger
from time import perf_counter
from typing import Generic, TypeVar

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.core.config import settings
from app.models.base import MongoDocument, now_utc

DocumentT = TypeVar("DocumentT", bound=MongoDocument)
mongo_logger = getLogger("app.mongo")


def start_mongo_timer() -> float:
    return perf_counter()


def log_slow_mongo_query(
    *,
    collection_name: str,
    operation: str,
    started_at: float,
    filters: dict | None = None,
) -> None:
    if not settings.request_timing_enabled:
        return
    duration_ms = (perf_counter() - started_at) * 1000
    if duration_ms < settings.request_slow_log_ms:
        return
    mongo_logger.warning(
        "mongo_slow_query collection=%s operation=%s duration_ms=%.2f filter_keys=%s",
        collection_name,
        operation,
        duration_ms,
        sorted((filters or {}).keys()),
    )


class BaseRepository(Generic[DocumentT], ABC):
    collection_name: str
    document_class: type[DocumentT]

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection: AsyncIOMotorCollection = db[self.collection_name]

    async def get_by_id(self, document_id: str) -> DocumentT | None:
        filters = {"_id": self._document_key(document_id)}
        started_at = start_mongo_timer()
        data = await self.collection.find_one(filters)
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="get_by_id",
            started_at=started_at,
            filters=filters,
        )
        return self.document_class.from_mongo(data)

    async def create(self, document: DocumentT) -> DocumentT:
        payload = document.to_mongo()
        if payload.get("_id") is None:
            payload.pop("_id", None)
        started_at = start_mongo_timer()
        result = await self.collection.insert_one(payload)
        created = await self.collection.find_one({"_id": result.inserted_id})
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="create",
            started_at=started_at,
            filters={"_id": result.inserted_id},
        )
        return self.document_class.from_mongo(created)

    async def update_by_id(self, document_id: str, updates: dict) -> DocumentT | None:
        updates["updated_at"] = now_utc()
        started_at = start_mongo_timer()
        await self.collection.update_one({"_id": self._document_key(document_id)}, {"$set": updates})
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="update_by_id",
            started_at=started_at,
            filters={"_id": self._document_key(document_id)},
        )
        return await self.get_by_id(document_id)

    async def delete_by_id(self, document_id: str) -> bool:
        filters = {"_id": self._document_key(document_id)}
        started_at = start_mongo_timer()
        result = await self.collection.delete_one(filters)
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="delete_by_id",
            started_at=started_at,
            filters=filters,
        )
        return result.deleted_count == 1

    def _document_key(self, document_id: str):
        return ObjectId(document_id) if ObjectId.is_valid(document_id) else document_id
