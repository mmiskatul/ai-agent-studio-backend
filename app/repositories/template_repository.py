from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.template import TemplateDocument
from app.repositories.base import BaseRepository


class TemplateRepository(BaseRepository[TemplateDocument]):
    collection_name = "templates"
    document_class = TemplateDocument

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db)

    async def list_all(self) -> list[TemplateDocument]:
        cursor = self.collection.find({}).sort("created_at", 1)
        templates: list[TemplateDocument] = []
        async for item in cursor:
            template = self.document_class.from_mongo(item)
            if template is not None:
                templates.append(template)
        return templates

    async def get_by_key(self, key: str) -> TemplateDocument | None:
        data = await self.collection.find_one({"key": key})
        return self.document_class.from_mongo(data)
