from app.models.base import MongoDocument


class KnowledgeChunkDocument(MongoDocument):
    knowledge_id: str
    agent_id: str
    user_id: str
    chunk_index: int
    content: str
    embedding: list[float]


class KnowledgeDocument(MongoDocument):
    user_id: str
    agent_id: str
    filename: str
    content_type: str | None = None
    cloudinary_url: str
    cloudinary_public_id: str | None = None
    chunk_count: int = 0
