from fastapi import HTTPException, status

from app.core.config import settings
from app.models.agent import AgentDocument
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

    async def create_chat(self, agent_id: str, user: UserDocument) -> ChatDocument:
        agent = await self._agents.get_owned(agent_id, user.id or "")
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

        return await self._chats.create(ChatDocument(user_id=user.id or "", agent_id=agent_id))

    async def list_chats(self, agent_id: str, user: UserDocument) -> list[ChatDocument]:
        agent = await self._agents.get_owned(agent_id, user.id or "")
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

        chats = await self._chats.list_by_agent(user.id or "", agent_id)
        for chat in chats:
            await self._ensure_chat_title(chat)
        return chats

    async def list_messages(self, chat_id: str) -> list[MessageDocument]:
        return await self._chats.list_messages(chat_id)

    async def list_chat_messages(
        self,
        agent_id: str,
        chat_id: str,
        user: UserDocument,
    ) -> list[MessageDocument]:
        chat = await self._get_owned_chat(agent_id, chat_id, user)
        return await self._chats.list_messages(chat.id or "")

    async def delete_message(self, agent_id: str, user: UserDocument, message_id: str) -> None:
        chat = await self.get_or_create_chat(agent_id, user)
        message = await self._get_owned_message(chat.id or "", message_id)
        deleted = await self._chats.delete_message(message.id or "")
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    async def delete_chat_message(
        self,
        agent_id: str,
        chat_id: str,
        user: UserDocument,
        message_id: str,
    ) -> None:
        chat = await self._get_owned_chat(agent_id, chat_id, user)
        message = await self._get_owned_message(chat.id or "", message_id)
        deleted = await self._chats.delete_message(message.id or "")
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    async def delete_chat(self, agent_id: str, chat_id: str, user: UserDocument) -> None:
        chat = await self._get_owned_chat(agent_id, chat_id, user)
        deleted = await self._chats.delete_chat(chat.id or "")
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

    async def update_user_message(
        self,
        agent_id: str,
        user: UserDocument,
        message_id: str,
        content: str,
    ) -> tuple[MessageDocument, MessageDocument]:
        agent = await self._agents.get_owned(agent_id, user.id or "")
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

        chat = await self.get_or_create_chat(agent_id, user)
        return await self._update_user_message_in_chat(agent, chat, message_id, content)

    async def update_chat_user_message(
        self,
        agent_id: str,
        chat_id: str,
        user: UserDocument,
        message_id: str,
        content: str,
    ) -> tuple[MessageDocument, MessageDocument]:
        agent = await self._agents.get_owned(agent_id, user.id or "")
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

        chat = await self._get_owned_chat(agent_id, chat_id, user)
        return await self._update_user_message_in_chat(agent, chat, message_id, content)

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
        return await self._send_message_to_chat(agent, chat, content)

    async def send_chat_message(
        self,
        agent_id: str,
        chat_id: str,
        user: UserDocument,
        content: str,
    ) -> tuple[MessageDocument, MessageDocument]:
        agent = await self._agents.get_owned(agent_id, user.id or "")
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

        chat = await self._get_owned_chat(agent_id, chat_id, user)
        return await self._send_message_to_chat(agent, chat, content)

    async def _get_owned_chat(
        self,
        agent_id: str,
        chat_id: str,
        user: UserDocument,
    ) -> ChatDocument:
        chat = await self._chats.get_owned_chat(user.id or "", agent_id, chat_id)
        if chat is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
        return chat

    async def _get_owned_message(self, chat_id: str, message_id: str) -> MessageDocument:
        message = await self._chats.get_message(message_id)
        if message is None or message.chat_id != chat_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
        return message

    async def _send_message_to_chat(
        self,
        agent: AgentDocument,
        chat: ChatDocument,
        content: str,
    ) -> tuple[MessageDocument, MessageDocument]:
        if not chat.title:
            await self._chats.update_chat_title(chat.id or "", self._build_chat_title(content))

        user_message = await self._chats.add_message(
            MessageDocument(chat_id=chat.id or "", sender_type="user", content=content),
        )

        assistant_content = await self._generate_assistant_response(agent, content)
        assistant_message = await self._chats.add_message(
            MessageDocument(
                chat_id=chat.id or "",
                sender_type="assistant",
                content=assistant_content,
            ),
        )

        return user_message, assistant_message

    async def _update_user_message_in_chat(
        self,
        agent: AgentDocument,
        chat: ChatDocument,
        message_id: str,
        content: str,
    ) -> tuple[MessageDocument, MessageDocument]:
        message = await self._get_owned_message(chat.id or "", message_id)
        if message.sender_type != "user":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only user messages can be edited",
            )

        updated_user_message = await self._chats.update_message_content(message.id or "", content)
        if updated_user_message is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        first_user_message = await self._chats.get_first_user_message(chat.id or "")
        if first_user_message is not None and first_user_message.id == message.id:
            await self._chats.update_chat_title(chat.id or "", self._build_chat_title(content))

        assistant_content = await self._generate_assistant_response(agent, content)
        next_assistant = await self._chats.get_next_assistant_message(
            chat.id or "",
            message.created_at,
        )
        if next_assistant is None:
            assistant_message = await self._chats.add_message(
                MessageDocument(
                    chat_id=chat.id or "",
                    sender_type="assistant",
                    content=assistant_content,
                ),
            )
        else:
            assistant_message = await self._chats.update_message_content(
                next_assistant.id or "",
                assistant_content,
            )
            if assistant_message is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        return updated_user_message, assistant_message

    def _build_chat_title(self, content: str) -> str:
        title = " ".join(content.strip().split())
        if len(title) <= 80:
            return title
        return f"{title[:77].rstrip()}..."

    async def _ensure_chat_title(self, chat: ChatDocument) -> None:
        if chat.title:
            return

        first_user_message = await self._chats.get_first_user_message(chat.id or "")
        if first_user_message is None:
            return

        title = self._build_chat_title(first_user_message.content)
        await self._chats.update_chat_title(chat.id or "", title)
        chat.title = title

    async def _generate_assistant_response(self, agent: AgentDocument, content: str) -> str:
        fallback = self._build_fallback_response(agent, content)
        if not settings.openai_api_key:
            return fallback

        try:
            from openai import AsyncOpenAI
            from openai import APIError, APIStatusError, RateLimitError
        except ImportError:
            return fallback

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        model = agent.llm_engine or settings.default_llm_engine

        try:
            response = await client.responses.create(
                model=model,
                instructions=agent.system_prompt,
                input=content,
                temperature=agent.temperature,
            )
        except (RateLimitError, APIStatusError, APIError):
            return fallback

        output_text = getattr(response, "output_text", None)
        if output_text:
            return output_text.strip()

        return fallback

    def _build_fallback_response(self, agent: AgentDocument, content: str) -> str:
        lowered_content = content.lower().strip()
        greeting_terms = {"hello", "hi", "hey", "good morning", "good afternoon", "good evening"}

        if lowered_content in greeting_terms:
            return agent.welcome_message or (
                f"Hi, I'm {agent.name}. I can help with {agent.purpose} "
                "Share what you need, and I'll guide you through the next best steps."
            )

        return (
            f"I can help with {agent.purpose}. "
            "Please share any relevant details, constraints, or goals, and I'll provide a clear next step."
        )
