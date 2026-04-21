from app.db.unit_of_work import UnitOfWork
from app.services.agent_service import AgentService
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.knowledge_service import KnowledgeService
from app.services.overview_service import OverviewService


class ServiceFactory:
    """Factory that wires services to a request-scoped UnitOfWork."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    @property
    def auth_service(self) -> AuthService:
        return AuthService(self._uow.users)

    @property
    def agent_service(self) -> AgentService:
        return AgentService(self._uow.agents)

    @property
    def chat_service(self) -> ChatService:
        return ChatService(self._uow.chats, self._uow.agents)

    @property
    def overview_service(self) -> OverviewService:
        return OverviewService(self._uow.agents, self._uow.chats)

    @property
    def knowledge_service(self) -> KnowledgeService:
        return KnowledgeService(self._uow.knowledge, self._uow.agents)
