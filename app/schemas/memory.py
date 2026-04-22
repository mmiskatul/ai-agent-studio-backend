from datetime import datetime

from pydantic import BaseModel, Field


class MemoryResponse(BaseModel):
    user_id: str
    session_id: str
    chat_id: str | None = None
    summary: str = ""
    facts: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    last_agent_id: str | None = None
    updated_at: datetime
