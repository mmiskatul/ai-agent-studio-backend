from fastapi import HTTPException, status

from app.models.chat import ChatDocument, MessageDocument
from app.models.user import UserDocument
from app.repositories.agent_repository import AgentRepository
from app.repositories.chat_repository import ChatRepository


class ChatService:
    def __init__(self, chats: ChatRepository, agents: AgentRepository) -> None:
        self._chats = chats
        self._agents = agents

    async def get_or_create_chat(self, agent_id: str, user: UserDocument) -> ChatDocument:
        agent = await self._agents.get_owned(agent_id, user.id or "")
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

        existing = await self._chats.get_for_agent(user.id or "", agent_id)
        if existing is not None:
            return existing

        return await self._chats.create(ChatDocument(user_id=user.id or "", agent_id=agent_id))

    async def list_messages(self, chat_id: str) -> list[MessageDocument]:
        return await self._chats.list_messages(chat_id)

    async def send_message(
        self,
        agent_id: str,
        user: UserDocument,
        content: str,
    ) -> tuple[MessageDocument, MessageDocument]:
        agent = await self._agents.get_owned(agent_id, user.id or "")
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

        chat = await self.get_or_create_chat(agent_id, user)
        user_message = await self._chats.add_message(
            MessageDocument(chat_id=chat.id or "", sender_type="user", content=content),
        )

        assistant_content = self._build_placeholder_response(agent.system_prompt, content)
        assistant_message = await self._chats.add_message(
            MessageDocument(
                chat_id=chat.id or "",
                sender_type="assistant",
                content=assistant_content,
            ),
        )

        return user_message, assistant_message

    def _build_placeholder_response(self, system_prompt: str, content: str) -> str:
        return (
            "Backend placeholder response. Add the LLM provider integration in ChatService "
            "when the provider is selected.\n\n"
            f"System prompt: {system_prompt}\n\n"
            f"User message: {content}"
        )
