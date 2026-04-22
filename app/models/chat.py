from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.base import MongoDocument, now_utc


class MessageDocument(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid4().hex}")
    chat_id: str
    sender_type: str
    content: str
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class ChatDocument(MongoDocument):
    id: str | None = Field(default_factory=lambda: f"chat_{uuid4().hex}", alias="_id")
    user_id: str
    agent_id: str
    agent_name: str | None = None
    title: str | None = None
    summary: str | None = None
    messages: list[MessageDocument] = Field(default_factory=list)
