from pydantic import Field

from app.models.base import MongoDocument
from app.models.chat import ChatDocument


class AgentDocument(MongoDocument):
    user_id: str = ""
    name: str
    role: str
    purpose: str = ""
    description: str | None = None
    template_type: str | None = None
    category_tag: str | None = None
    system_prompt: str
    welcome_message: str | None = None
    llm_engine: str = "gpt-4o"
    model: str | None = None
    temperature: float = 0.7
    status: str = "active"
    tools: list[str] = Field(default_factory=list)
    routing_keywords: list[str] = Field(default_factory=list)
    priority: int = 100
    is_active: bool = True
    chats: list[ChatDocument] = Field(default_factory=list)
