from datetime import datetime

from pydantic import BaseModel


class TemplateResponse(BaseModel):
    id: str
    key: str
    label: str
    name: str
    role: str
    description: str
    language: str
    system_prompt: str
    created_at: datetime
    updated_at: datetime
