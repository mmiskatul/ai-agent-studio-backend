from datetime import datetime
from uuid import uuid4

from pydantic import Field, model_validator

from app.models.base import MongoDocument, now_utc


class MessageRecord(MongoDocument):
    id: str | None = Field(default_factory=lambda: f"msg_{uuid4().hex}", alias="_id")
    user_id: str
    session_id: str
    chat_id: str
    agent_id: str | None = None
    role: str
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

    @model_validator(mode="before")
    @classmethod
    def normalize_role(cls, data):
        if isinstance(data, dict) and "role" not in data and "sender_type" in data:
            data = dict(data)
            data["role"] = data["sender_type"]
        return data

    @property
    def sender_type(self) -> str:
        return self.role
