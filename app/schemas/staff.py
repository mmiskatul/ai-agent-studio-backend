from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class StaffCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr
    role: str = Field(min_length=1, max_length=120)
    assigned_agent_ids: list[str] = Field(default_factory=list)


class StaffUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    email: EmailStr | None = None
    role: str | None = Field(default=None, min_length=1, max_length=120)
    assigned_agent_ids: list[str] | None = None


class StaffResponse(BaseModel):
    id: str
    user_id: str
    name: str
    email: EmailStr
    role: str
    assigned_agent_ids: list[str]
    created_at: datetime
    updated_at: datetime
