from app.models.base import MongoDocument


class AgentDocument(MongoDocument):
    user_id: str
    name: str
    role: str
    purpose: str
    template_type: str | None = None
    system_prompt: str
    status: str = "active"
