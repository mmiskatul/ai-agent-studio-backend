from pydantic import Field

from app.models.base import MongoDocument


class TemplateDocument(MongoDocument):
    id: str = Field(alias="_id")
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1500)
    language: str = "EN"
    system_prompt: str = Field(min_length=1)
