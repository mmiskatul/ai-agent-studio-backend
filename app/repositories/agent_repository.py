from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.agent import AgentDocument
from app.repositories.base import BaseRepository, log_slow_mongo_query, start_mongo_timer

AGENT_LIST_PROJECTION = {"chats": 0}
AGENT_SUMMARY_PROJECTION = {
    "_id": 1,
    "user_id": 1,
    "name": 1,
    "role": 1,
    "template_type": 1,
    "status": 1,
    "created_at": 1,
    "updated_at": 1,
}


class AgentRepository(BaseRepository[AgentDocument]):
    collection_name = "agents"
    document_class = AgentDocument

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db)

    async def list_by_user(self, user_id: str) -> list[AgentDocument]:
        filters = {"user_id": user_id}
        started_at = start_mongo_timer()
        cursor = self.collection.find(filters, AGENT_LIST_PROJECTION).sort("created_at", -1)
        agents: list[AgentDocument] = []
        async for item in cursor:
            agent = self.document_class.from_mongo(item)
            if agent is not None:
                agents.append(agent)
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="list_by_user",
            started_at=started_at,
            filters=filters,
        )
        return agents

    async def list_summaries_by_user(self, user_id: str) -> list[dict]:
        filters = {"user_id": user_id}
        started_at = start_mongo_timer()
        cursor = self.collection.find(filters, AGENT_SUMMARY_PROJECTION).sort("created_at", -1)
        agents = [item async for item in cursor]
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="list_summaries_by_user",
            started_at=started_at,
            filters=filters,
        )
        return agents

    async def get_owned(self, agent_id: str, user_id: str) -> AgentDocument | None:
        filters = {"_id": self._document_key(agent_id), "user_id": user_id}
        started_at = start_mongo_timer()
        data = await self.collection.find_one(filters, AGENT_LIST_PROJECTION)
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="get_owned",
            started_at=started_at,
            filters=filters,
        )
        return self.document_class.from_mongo(data)

    async def delete_owned(self, agent_id: str, user_id: str) -> bool:
        result = await self.collection.delete_one(
            {"_id": self._document_key(agent_id), "user_id": user_id}
        )
        return result.deleted_count == 1

    async def list_active_by_user(self, user_id: str) -> list[AgentDocument]:
        filters = {"user_id": user_id, "is_active": True, "status": "enabled"}
        started_at = start_mongo_timer()
        cursor = self.collection.find(filters, AGENT_LIST_PROJECTION).sort(
            [("priority", 1), ("created_at", -1)]
        )
        agents: list[AgentDocument] = []
        async for item in cursor:
            agent = self.document_class.from_mongo(item)
            if agent is not None:
                agents.append(agent)
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="list_active_by_user",
            started_at=started_at,
            filters=filters,
        )
        return agents
