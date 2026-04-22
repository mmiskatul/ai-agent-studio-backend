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
        agents: list[AgentDocument] = []
        async for item in cursor:
            agent = self.document_class.from_mongo(item)
            if agent is not None:
                agents.append(agent)
        return agents

    async def get_owned(self, agent_id: str, user_id: str) -> AgentDocument | None:
        data = await self.collection.find_one(
            {"_id": self._document_key(agent_id), "user_id": user_id}
        )
        return self.document_class.from_mongo(data)

    async def delete_owned(self, agent_id: str, user_id: str) -> bool:
        result = await self.collection.delete_one(
            {"_id": self._document_key(agent_id), "user_id": user_id}
        )
        return result.deleted_count == 1

    async def list_active_by_user(self, user_id: str) -> list[AgentDocument]:
        cursor = self.collection.find(
            {"user_id": user_id, "is_active": True, "status": "active"}
        ).sort([("priority", 1), ("created_at", -1)])
        agents: list[AgentDocument] = []
        async for item in cursor:
            agent = self.document_class.from_mongo(item)
            if agent is not None:
                agents.append(agent)
        return agents
