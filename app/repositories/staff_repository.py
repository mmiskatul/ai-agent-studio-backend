from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.staff import StaffDocument
from app.repositories.base import BaseRepository, log_slow_mongo_query, start_mongo_timer


class StaffRepository(BaseRepository[StaffDocument]):
    collection_name = "staff"
    document_class = StaffDocument

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db)

    async def list_by_user(self, user_id: str) -> list[StaffDocument]:
        filters = {"user_id": user_id}
        started_at = start_mongo_timer()
        cursor = self.collection.find(filters).sort("created_at", -1)
        members: list[StaffDocument] = []
        async for item in cursor:
            member = self.document_class.from_mongo(item)
            if member is not None:
                members.append(member)
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="list_by_user",
            started_at=started_at,
            filters=filters,
        )
        return members

    async def count_by_user(self, user_id: str) -> int:
        filters = {"user_id": user_id}
        started_at = start_mongo_timer()
        count = await self.collection.count_documents(filters)
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="count_by_user",
            started_at=started_at,
            filters=filters,
        )
        return count

    async def get_owned(self, staff_id: str, user_id: str) -> StaffDocument | None:
        data = await self.collection.find_one({"_id": self._document_key(staff_id), "user_id": user_id})
        return self.document_class.from_mongo(data)

    async def delete_owned(self, staff_id: str, user_id: str) -> bool:
        result = await self.collection.delete_one({"_id": self._document_key(staff_id), "user_id": user_id})
        return result.deleted_count == 1
