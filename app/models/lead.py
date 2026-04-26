from pydantic import Field

from app.models.base import MongoDocument


class LeadDocument(MongoDocument):
    user_id: str
    agent_id: str
    name: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=2000)
