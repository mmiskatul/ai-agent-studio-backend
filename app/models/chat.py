from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from app.models.base import MongoDocument, now_utc


class MessageDocument(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid4().hex}")
    chat_id: str
    agent_id: str | None = None
    user_id: str | None = None
    sender_type: str
    role: str | None = None
    content: str
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class ChatMemoryDocument(BaseModel):
    title: str = ""
    running_summary: str = ""
    facts: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    open_loops: list[str] = Field(default_factory=list)
    recent_topics: list[str] = Field(default_factory=list)
    last_user_goal: str = ""
    last_updated_at: datetime | None = None


class ChatDocument(MongoDocument):
    id: str | None = Field(default_factory=lambda: f"chat_{uuid4().hex}", alias="_id")
    user_id: str
    agent_id: str
    current_agent_id: str | None = None
    session_id: str | None = None
    agent_name: str | None = None
    title: str | None = None
    summary: str | None = None
    memory: ChatMemoryDocument | None = None
    messages: list[MessageDocument] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_current_agent(cls, data):
        if isinstance(data, dict) and "current_agent_id" not in data and "agent_id" in data:
            data = dict(data)
            data["current_agent_id"] = data["agent_id"]
        return data
