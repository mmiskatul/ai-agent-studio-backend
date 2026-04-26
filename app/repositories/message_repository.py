from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.base import now_utc
from app.models.message import MessageRecord
from app.repositories.base import BaseRepository, log_slow_mongo_query, start_mongo_timer


class MessageRepository(BaseRepository[MessageRecord]):
    collection_name = "messages"
    document_class = MessageRecord

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db)

    async def list_by_chat(self, user_id: str, chat_id: str, limit: int = 50) -> list[MessageRecord]:
        filters = {"user_id": user_id, "chat_id": chat_id}
        started_at = start_mongo_timer()
        cursor = (
            self.collection.find(filters)
            .sort("created_at", -1)
            .limit(limit)
        )
        messages = [message async for message in self._iterate(cursor)]
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="list_by_chat",
            started_at=started_at,
            filters=filters,
        )
        return list(reversed(messages))

    async def list_by_session(
        self,
        user_id: str,
        session_id: str,
        limit: int = 100,
    ) -> list[MessageRecord]:
        filters = {"user_id": user_id, "session_id": session_id}
        started_at = start_mongo_timer()
        cursor = (
            self.collection.find(filters)
            .sort("created_at", -1)
            .limit(limit)
        )
        messages = [message async for message in self._iterate(cursor)]
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="list_by_session",
            started_at=started_at,
            filters=filters,
        )
        return list(reversed(messages))

    async def create_message(self, message: MessageRecord) -> MessageRecord:
        created = await self.create(message)
        return created

    async def mark_chat_agent(self, chat_id: str, agent_id: str) -> None:
        await self.collection.update_many(
            {"chat_id": chat_id, "agent_id": None},
            {"$set": {"agent_id": agent_id, "updated_at": now_utc()}},
        )

    async def count_user_messages_by_agent(
        self,
        user_id: str,
        *,
        since=None,
        agent_ids: list[str] | None = None,
    ) -> dict[str, int]:
        match: dict = {
            "user_id": user_id,
            "agent_id": {"$type": "string", "$ne": ""},
            "$or": [{"role": "user"}, {"sender_type": "user"}],
        }
        if since is not None:
            match["created_at"] = {"$gte": since}
        if agent_ids is not None:
            match["agent_id"]["$in"] = agent_ids

        pipeline = [
            {"$match": match},
            {"$group": {"_id": "$agent_id", "count": {"$sum": 1}}},
        ]
        counts: dict[str, int] = {}
        started_at = start_mongo_timer()
        async for item in self.collection.aggregate(pipeline):
            agent_id = item.get("_id")
            if isinstance(agent_id, str) and agent_id:
                counts[agent_id] = int(item.get("count", 0))
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="count_user_messages_by_agent",
            started_at=started_at,
            filters={"user_id": user_id, "agent_id": "scoped"},
        )
        return counts

    async def count_messages_by_user(self, user_id: str) -> int:
        filters = {"user_id": user_id, "agent_id": {"$type": "string", "$ne": ""}}
        started_at = start_mongo_timer()
        count = await self.collection.count_documents(
            filters,
        )
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="count_messages_by_user",
            started_at=started_at,
            filters={"user_id": user_id, "agent_id": "string"},
        )
        return count

    async def _iterate(self, cursor):
        async for item in cursor:
            message = self.document_class.from_mongo(item)
            if message is not None:
                yield message
