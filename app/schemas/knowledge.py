from datetime import datetime

from pydantic import BaseModel


class KnowledgeResponse(BaseModel):
    id: str
    user_id: str
    agent_id: str
    filename: str
    content_type: str | None = None
    cloudinary_url: str
    cloudinary_public_id: str | None = None
    chunk_count: int
    created_at: datetime
    updated_at: datetime
