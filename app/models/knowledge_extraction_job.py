from uuid import uuid4

from pydantic import Field

from app.models.base import MongoDocument


class KnowledgeExtractionJobDocument(MongoDocument):
    id: str | None = Field(default_factory=lambda: f"knowledge_job_{uuid4().hex}", alias="_id")
    user_id: str
    status: str = "pending"
    file_name: str
    content_type: str = "application/octet-stream"
    extracted_text: str | None = None
    character_count: int = 0
    error: str | None = None
