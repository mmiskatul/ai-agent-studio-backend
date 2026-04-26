from pydantic import EmailStr, Field

from app.models.base import MongoDocument


class StaffDocument(MongoDocument):
    user_id: str
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr
    role: str = Field(min_length=1, max_length=120)
    assigned_agent_ids: list[str] = Field(default_factory=list)
