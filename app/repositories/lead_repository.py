from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.lead import LeadDocument
from app.repositories.base import BaseRepository, log_slow_mongo_query, start_mongo_timer


class LeadRepository(BaseRepository[LeadDocument]):
    collection_name = "leads"
    document_class = LeadDocument

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db)

    async def list_by_user(self, user_id: str) -> list[LeadDocument]:
        filters = {"user_id": user_id}
        started_at = start_mongo_timer()
        cursor = self.collection.find(filters).sort("created_at", -1)
        leads: list[LeadDocument] = []
        async for item in cursor:
            lead = self.document_class.from_mongo(item)
            if lead is not None:
                leads.append(lead)
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="list_by_user",
            started_at=started_at,
            filters=filters,
        )
        return leads

    async def list_by_agent(self, user_id: str, agent_id: str) -> list[LeadDocument]:
        filters = {"user_id": user_id, "agent_id": agent_id}
        started_at = start_mongo_timer()
        cursor = self.collection.find(filters).sort("created_at", -1)
        leads: list[LeadDocument] = []
        async for item in cursor:
            lead = self.document_class.from_mongo(item)
            if lead is not None:
                leads.append(lead)
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="list_by_agent",
            started_at=started_at,
            filters=filters,
        )
        return leads

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
