from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.models.base import now_utc
from app.models.knowledge_extraction_job import KnowledgeExtractionJobDocument
from app.repositories.base import BaseRepository, log_slow_mongo_query, start_mongo_timer


class KnowledgeExtractionJobRepository(BaseRepository[KnowledgeExtractionJobDocument]):
    collection_name = "knowledge_extraction_jobs"
    document_class = KnowledgeExtractionJobDocument

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db)

    async def get_owned(self, job_id: str, user_id: str) -> KnowledgeExtractionJobDocument | None:
        filters = {"_id": self._document_key(job_id), "user_id": user_id}
        started_at = start_mongo_timer()
        data = await self.collection.find_one(filters)
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="get_owned",
            started_at=started_at,
            filters=filters,
        )
        return self.document_class.from_mongo(data)

    async def update_status(
        self,
        job_id: str,
        *,
        status: str,
        extracted_text: str | None = None,
        character_count: int | None = None,
        error: str | None = None,
    ) -> KnowledgeExtractionJobDocument | None:
        updates: dict[str, object] = {
            "status": status,
            "updated_at": now_utc(),
        }
        if extracted_text is not None:
            updates["extracted_text"] = extracted_text
        if character_count is not None:
            updates["character_count"] = character_count
        if error is not None:
            updates["error"] = error
        elif status == "completed":
            updates["error"] = None

        started_at = start_mongo_timer()
        data = await self.collection.find_one_and_update(
            {"_id": self._document_key(job_id)},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        log_slow_mongo_query(
            collection_name=self.collection_name,
            operation="update_status",
            started_at=started_at,
            filters={"_id": self._document_key(job_id)},
        )
        return self.document_class.from_mongo(data)
