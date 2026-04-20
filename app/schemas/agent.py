from datetime import datetime

from pydantic import BaseModel, Field


class AgentBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=160)
    purpose: str = Field(min_length=1, max_length=500)
    template_type: str | None = None
    system_prompt: str = Field(min_length=1)
    status: str = "active"


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, min_length=1, max_length=160)
    purpose: str | None = Field(default=None, min_length=1, max_length=500)
    template_type: str | None = None
    system_prompt: str | None = Field(default=None, min_length=1)
    status: str | None = None


class AgentResponse(AgentBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
