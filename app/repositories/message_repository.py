from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.base import now_utc
from app.models.message import MessageRecord
from app.repositories.base import BaseRepository


class MessageRepository(BaseRepository[MessageRecord]):
    collection_name = "messages"
    document_class = MessageRecord

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db)

    async def list_by_chat(self, user_id: str, chat_id: str, limit: int = 50) -> list[MessageRecord]:
        cursor = (
            self.collection.find({"user_id": user_id, "chat_id": chat_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        messages = [message async for message in self._iterate(cursor)]
        return list(reversed(messages))

    async def list_by_session(
        self,
        user_id: str,
        session_id: str,
        limit: int = 100,
    ) -> list[MessageRecord]:
        cursor = (
            self.collection.find({"user_id": user_id, "session_id": session_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        messages = [message async for message in self._iterate(cursor)]
        return list(reversed(messages))

    async def create_message(self, message: MessageRecord) -> MessageRecord:
        created = await self.create(message)
        return created

    async def mark_chat_agent(self, chat_id: str, agent_id: str) -> None:
        await self.collection.update_many(
            {"chat_id": chat_id, "agent_id": None},
            {"$set": {"agent_id": agent_id, "updated_at": now_utc()}},
        )

    async def _iterate(self, cursor):
        async for item in cursor:
            message = self.document_class.from_mongo(item)
            if message is not None:
                yield message
