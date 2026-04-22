from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.base import now_utc
from app.models.memory import MemoryRecord
from app.repositories.base import BaseRepository


class MemoryRepository(BaseRepository[MemoryRecord]):
    collection_name = "memory"
    document_class = MemoryRecord

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db)

    async def get_for_session(self, user_id: str, session_id: str) -> MemoryRecord | None:
        data = await self.collection.find_one({"user_id": user_id, "session_id": session_id})
        return self.document_class.from_mongo(data)

    async def upsert_session_memory(
        self,
        *,
        user_id: str,
        session_id: str,
        chat_id: str | None,
        summary: str,
        facts: list[str],
        preferences: list[str],
        last_agent_id: str | None,
    ) -> MemoryRecord:
        now = now_utc()
        await self.collection.update_one(
            {"user_id": user_id, "session_id": session_id},
            {
                "$set": {
                    "chat_id": chat_id,
                    "summary": summary,
                    "facts": facts,
                    "preferences": preferences,
                    "last_agent_id": last_agent_id,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        memory = await self.get_for_session(user_id, session_id)
        if memory is None:
            return MemoryRecord(
                user_id=user_id,
                session_id=session_id,
                chat_id=chat_id,
                summary=summary,
                facts=facts,
                preferences=preferences,
                last_agent_id=last_agent_id,
                updated_at=now,
            )
        return memory
