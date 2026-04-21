from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.agent_repository import AgentRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.user_repository import UserRepository


class UnitOfWork:
    """Groups repositories for request-scoped service operations."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.users = UserRepository(db)
        self.agents = AgentRepository(db)
        self.chats = ChatRepository(db)
