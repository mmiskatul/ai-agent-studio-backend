from app.models.base import MongoDocument


class AgentDocument(MongoDocument):
    user_id: str
    name: str
    role: str
    purpose: str
    template_type: str | None = None
    category_tag: str | None = None
    system_prompt: str
    welcome_message: str | None = None
    llm_engine: str = "gpt-4o"
    temperature: float = 0.7
    status: str = "active"
