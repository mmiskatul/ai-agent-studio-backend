from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.agent import AgentDocument
from app.repositories.base import BaseRepository


class AgentRepository(BaseRepository[AgentDocument]):
    collection_name = "agents"
    document_class = AgentDocument

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db)

    async def list_by_user(self, user_id: str) -> list[AgentDocument]:
        cursor = self.collection.find({"user_id": user_id}).sort("created_at", -1)
        return [self.document_class.from_mongo(item) async for item in cursor]

    async def get_owned(self, agent_id: str, user_id: str) -> AgentDocument | None:
        if not ObjectId.is_valid(agent_id):
            return None
        data = await self.collection.find_one({"_id": ObjectId(agent_id), "user_id": user_id})
        return self.document_class.from_mongo(data)

    async def delete_owned(self, agent_id: str, user_id: str) -> bool:
        if not ObjectId.is_valid(agent_id):
            return False
        result = await self.collection.delete_one({"_id": ObjectId(agent_id), "user_id": user_id})
        return result.deleted_count == 1
