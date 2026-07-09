from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.agent_repository import AgentRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.knowledge_extraction_job_repository import KnowledgeExtractionJobRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.template_repository import TemplateRepository
from app.repositories.user_repository import UserRepository


class UnitOfWork:
    """Groups repositories for request-scoped service operations."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.users = UserRepository(db)
        self.agents = AgentRepository(db)
        self.chats = ChatRepository(db)
        self.messages = MessageRepository(db)
        self.memory = MemoryRepository(db)
        self.knowledge_extraction_jobs = KnowledgeExtractionJobRepository(db)
        self.templates = TemplateRepository(db)
