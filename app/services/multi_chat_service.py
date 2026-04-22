from fastapi import HTTPException, status

from app.graph.builder import ChatGraphBuilder
from app.repositories.agent_repository import AgentRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.chat import ChatStructuredResponse
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.services.router_service import RouterService


class MultiChatService:
    def __init__(
        self,
        *,
        agents: AgentRepository,
        chats: ChatRepository,
        messages: MessageRepository,
        memories: MemoryRepository,
    ) -> None:
        self._agents = agents
        self._chats = chats
        self._messages = messages
        self._memories = memories
        self._llm = LLMService()
        self._memory = MemoryService(memories, self._llm)
        self._router = RouterService(self._llm)

    async def send(
        self,
        *,
        user_id: str,
        message: str,
        session_id: str | None,
        chat_id: str | None,
        agent_id: str | None,
    ) -> ChatStructuredResponse:
        graph = ChatGraphBuilder(
            agents=self._agents,
            chats=self._chats,
            messages=self._messages,
            router_service=self._router,
            llm_service=self._llm,
            memory_service=self._memory,
        ).build()
        try:
            state = await graph.ainvoke(
                {
                    "user_id": user_id,
                    "session_id": session_id or "",
                    "chat_id": chat_id or "",
                    "requested_agent_id": agent_id,
                    "user_message": message,
                }
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Chat workflow failed.",
            ) from exc
        return ChatStructuredResponse.model_validate(state["response_json"])

    async def history(self, *, user_id: str, session_id: str):
        chats = await self._chats.list_by_session(user_id, session_id)
        messages = await self._messages.list_by_session(user_id, session_id, limit=500)
        return chats, messages
