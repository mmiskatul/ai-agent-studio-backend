from app.models.base import MongoDocument


class ChatDocument(MongoDocument):
    user_id: str
    agent_id: str
    title: str | None = None


class MessageDocument(MongoDocument):
    chat_id: str
    sender_type: str
    content: str
