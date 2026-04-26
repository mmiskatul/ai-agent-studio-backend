from datetime import datetime

from pydantic import BaseModel, Field


class LeadCreate(BaseModel):
    agent_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=2000)


class LeadResponse(BaseModel):
    id: str
    agent_id: str
    user_id: str
    name: str
    phone: str
    message: str
    created_at: datetime
    updated_at: datetime
