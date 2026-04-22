from datetime import datetime

from pydantic import Field

from app.models.base import MongoDocument, now_utc


class MemoryRecord(MongoDocument):
    user_id: str
    session_id: str
    chat_id: str | None = None
    summary: str = ""
    facts: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    last_agent_id: str | None = None
    updated_at: datetime = Field(default_factory=now_utc)
