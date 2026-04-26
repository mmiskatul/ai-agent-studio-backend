from functools import cached_property

from app.db.unit_of_work import UnitOfWork
from app.services.agent_service import AgentService
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.lead_service import LeadService
from app.services.multi_chat_service import MultiChatService
from app.services.overview_service import OverviewService
from app.services.staff_service import StaffService
from app.services.template_service import TemplateService


class ServiceFactory:
    """Factory that wires services to a request-scoped UnitOfWork."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    @cached_property
    def auth_service(self) -> AuthService:
        return AuthService(self._uow.users, self._uow.agents, self._uow.chats)

    @cached_property
    def agent_service(self) -> AgentService:
        return AgentService(self._uow.agents, self._uow.chats, self._uow.messages)

    @cached_property
    def chat_service(self) -> ChatService:
        return ChatService(self._uow.chats, self._uow.agents)

    @cached_property
    def multi_chat_service(self) -> MultiChatService:
        return MultiChatService(
            agents=self._uow.agents,
            chats=self._uow.chats,
            messages=self._uow.messages,
            memories=self._uow.memory,
        )

    @cached_property
    def overview_service(self) -> OverviewService:
        return OverviewService(
            self._uow.agents,
            self._uow.chats,
            self._uow.messages,
            self._uow.leads,
            self._uow.staff,
        )

    @cached_property
    def template_service(self) -> TemplateService:
        return TemplateService(self._uow.templates)

    @cached_property
    def lead_service(self) -> LeadService:
        return LeadService(self._uow.leads, self._uow.agents)

    @cached_property
    def staff_service(self) -> StaffService:
        return StaffService(self._uow.staff, self._uow.agents)
