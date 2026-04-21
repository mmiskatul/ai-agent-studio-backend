from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.knowledge import KnowledgeChunkDocument, KnowledgeDocument
from app.repositories.base import BaseRepository


class KnowledgeRepository(BaseRepository[KnowledgeDocument]):
    collection_name = "knowledge"
    document_class = KnowledgeDocument

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db)
        self.chunks = db["knowledge_chunks"]

    async def list_by_agent(self, user_id: str, agent_id: str) -> list[KnowledgeDocument]:
        cursor = self.collection.find({"user_id": user_id, "agent_id": agent_id}).sort(
            "created_at",
            -1,
        )
        return [self.document_class.from_mongo(item) async for item in cursor]

    async def create_chunks(
        self,
        chunks: list[KnowledgeChunkDocument],
    ) -> list[KnowledgeChunkDocument]:
        if not chunks:
            return []

        payloads = []
        for chunk in chunks:
            payload = chunk.to_mongo()
            payload.pop("_id", None)
            payloads.append(payload)

        await self.chunks.insert_many(payloads)
        cursor = self.chunks.find({"knowledge_id": chunks[0].knowledge_id}).sort("chunk_index", 1)
        return [KnowledgeChunkDocument.from_mongo(item) async for item in cursor]
