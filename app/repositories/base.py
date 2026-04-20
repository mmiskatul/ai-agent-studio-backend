from abc import ABC
from typing import Generic, TypeVar

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.models.base import MongoDocument, now_utc

DocumentT = TypeVar("DocumentT", bound=MongoDocument)


class BaseRepository(Generic[DocumentT], ABC):
    collection_name: str
    document_class: type[DocumentT]

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection: AsyncIOMotorCollection = db[self.collection_name]

    async def get_by_id(self, document_id: str) -> DocumentT | None:
        if not ObjectId.is_valid(document_id):
            return None
        data = await self.collection.find_one({"_id": ObjectId(document_id)})
        return self.document_class.from_mongo(data)

    async def create(self, document: DocumentT) -> DocumentT:
        payload = document.to_mongo()
        payload.pop("_id", None)
        result = await self.collection.insert_one(payload)
        created = await self.collection.find_one({"_id": result.inserted_id})
        return self.document_class.from_mongo(created)

    async def update_by_id(self, document_id: str, updates: dict) -> DocumentT | None:
        if not ObjectId.is_valid(document_id):
            return None
        updates["updated_at"] = now_utc()
        await self.collection.update_one({"_id": ObjectId(document_id)}, {"$set": updates})
        return await self.get_by_id(document_id)

    async def delete_by_id(self, document_id: str) -> bool:
        if not ObjectId.is_valid(document_id):
            return False
        result = await self.collection.delete_one({"_id": ObjectId(document_id)})
        return result.deleted_count == 1
