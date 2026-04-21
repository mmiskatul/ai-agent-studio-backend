from fastapi import HTTPException, status

from app.agents.config import AgentConfig
from app.agents.platform import AgentPlatform
from app.core.config import settings
from app.models.agent import AgentDocument
from app.models.chat import ChatDocument, MessageDocument
from app.models.user import UserDocument
from app.repositories.agent_repository import AgentRepository
from app.repositories.chat_repository import ChatRepository
from app.tools.registry import default_tool_registry


class ChatService:
    def __init__(self, chats: ChatRepository, agents: AgentRepository) -> None:
        self._chats = chats
        self._agents = agents

    async def get_or_create_chat(self, agent_id: str, user: UserDocument) -> ChatDocument:
        self._ensure_agent_active(await self._get_owned_agent(agent_id, user))

        existing = await self._chats.get_for_agent(user.id or "", agent_id)
        if existing is not None:
            return existing

        return await self._chats.create(ChatDocument(user_id=user.id or "", agent_id=agent_id))

    async def create_chat(self, agent_id: str, user: UserDocument) -> ChatDocument:
        self._ensure_agent_active(await self._get_owned_agent(agent_id, user))

        return await self._chats.create(ChatDocument(user_id=user.id or "", agent_id=agent_id))

    async def list_chats(self, agent_id: str, user: UserDocument) -> list[ChatDocument]:
        self._ensure_agent_active(await self._get_owned_agent(agent_id, user))

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
        self._ensure_agent_active(await self._get_owned_agent(agent_id, user))
        chat = await self._get_owned_chat(agent_id, chat_id, user)
        return await self._chats.list_messages(chat.id or "")

    async def delete_message(self, agent_id: str, user: UserDocument, message_id: str) -> None:
        self._ensure_agent_active(await self._get_owned_agent(agent_id, user))
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
        self._ensure_agent_active(await self._get_owned_agent(agent_id, user))
        chat = await self._get_owned_chat(agent_id, chat_id, user)
        message = await self._get_owned_message(chat.id or "", message_id)
        deleted = await self._chats.delete_message(message.id or "")
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    async def delete_chat(self, agent_id: str, chat_id: str, user: UserDocument) -> None:
        self._ensure_agent_active(await self._get_owned_agent(agent_id, user))
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
        agent = await self._get_owned_agent(agent_id, user)
        self._ensure_agent_active(agent)

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
        agent = await self._get_owned_agent(agent_id, user)
        self._ensure_agent_active(agent)

        chat = await self._get_owned_chat(agent_id, chat_id, user)
        return await self._update_user_message_in_chat(agent, chat, message_id, content)

    async def send_message(
        self,
        agent_id: str,
        user: UserDocument,
        content: str,
    ) -> tuple[MessageDocument, MessageDocument]:
        agent = await self._get_owned_agent(agent_id, user)
        self._ensure_agent_active(agent)

        chat = await self.get_or_create_chat(agent_id, user)
        return await self._send_message_to_chat(agent, chat, content)

    async def send_chat_message(
        self,
        agent_id: str,
        chat_id: str,
        user: UserDocument,
        content: str,
    ) -> tuple[MessageDocument, MessageDocument]:
        agent = await self._get_owned_agent(agent_id, user)
        self._ensure_agent_active(agent)

        chat = await self._get_owned_chat(agent_id, chat_id, user)
        return await self._send_message_to_chat(agent, chat, content)

    async def _get_owned_agent(self, agent_id: str, user: UserDocument) -> AgentDocument:
        agent = await self._agents.get_owned(agent_id, user.id or "")
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        return agent

    def _ensure_agent_active(self, agent: AgentDocument) -> None:
        if agent.is_active and agent.status == "active":
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This agent is inactive and cannot be used for chat.",
        )

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
        title = self._build_chat_title(content)
        await self._chats.update_chat_title(chat.id or "", title)
        chat.title = title

        user_message = await self._chats.add_message(
            MessageDocument(chat_id=chat.id or "", sender_type="user", content=content),
        )

        messages = await self._chats.list_messages(chat.id or "")
        assistant_content = await self._generate_assistant_response(agent, content, messages)
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

        messages = await self._chats.list_messages(chat.id or "")
        assistant_content = await self._generate_assistant_response(agent, content, messages)
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
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Message not found",
                )

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

    async def _generate_assistant_response(
        self,
        agent: AgentDocument,
        content: str,
        messages: list[MessageDocument] | None = None,
    ) -> str:
        runtime_agent = self._build_agent_runtime_config(agent)
        history = self._message_history(messages or [], current_message=content)
        platform = AgentPlatform(
            configs=[runtime_agent],
            tool_registry=default_tool_registry(),
            llm=self._generate_openai_response,
        )
        return await platform.run(content, agent_key=runtime_agent.id, history=history)

    def _build_agent_runtime_config(self, agent: AgentDocument) -> AgentConfig:
        return AgentConfig(
            id=agent.id or agent.name,
            name=agent.name,
            description=agent.purpose,
            system_prompt=self._build_runtime_system_prompt(agent),
            tools=agent.tools or self._infer_tool_names(agent),
            model=agent.model or agent.llm_engine or settings.default_llm_engine,
            temperature=agent.temperature,
            is_active=agent.is_active and agent.status == "active",
        )

    def _build_runtime_system_prompt(self, agent: AgentDocument) -> str:
        return (
            f"{agent.system_prompt.strip()}\n\n"
            "High-quality response rules:\n"
            "- Answer the user's exact request first; do not introduce yourself or repeat the agent description.\n"
            "- Choose the best answer format for the question: direct answer, step-by-step plan, checklist, table, script, code, analysis, comparison, or troubleshooting flow.\n"
            "- Start with a short conclusion or recommendation, then explain the practical details.\n"
            "- Use the agent's role, purpose, available tools, and conversation history to tailor the answer.\n"
            "- Reuse the user's exact details such as product, channel, audience, numbers, goal, constraints, tone, or platform.\n"
            "- Give specific, practical, and complete guidance so the user can act without asking the same question again.\n"
            "- Include concrete examples, scripts, calculations, tables, templates, or ready-to-use copy when useful.\n"
            "- For sales or marketing questions, include positioning, offer, audience, content/caption, CTA, follow-up, and improvement loop when relevant.\n"
            "- For support or troubleshooting questions, include likely cause, diagnostic steps, fix steps, escalation rule, and a ready-to-send reply when relevant.\n"
            "- For data or analysis questions, include metric definition, method, evidence needed, interpretation, and recommendation when relevant.\n"
            "- For writing requests, produce the actual draft first, then optional notes for improvement.\n"
            "- For coding or technical requests, provide the concrete implementation or commands first, then explain important decisions.\n"
            "- State assumptions briefly when information is missing, then continue with the strongest useful answer.\n"
            "- Ask at most one clarifying question, and only after giving the best possible answer from available context.\n"
            "- Avoid vague filler, generic placeholders, repeated wording, and copy-pasted answers across turns.\n"
            "- Use clean Markdown with short sections and bullets when it improves readability.\n"
            "- Stay in the agent role and focus on the agent purpose."
        )

    def _infer_tool_names(self, agent: AgentDocument) -> list[str]:
        role_text = " ".join(
            [
                agent.name,
                agent.role,
                agent.purpose,
                agent.template_type or "",
                agent.category_tag or "",
            ]
        ).lower()
        tools = ["summarizer"]
        if any(term in role_text for term in ("sales", "lead", "revenue", "marketing")):
            tools.append("sales_playbook")
        if any(term in role_text for term in ("data", "analytics", "report", "metric")):
            tools.append("calculator")
        return tools

    async def _generate_openai_response(
        self,
        agent_config: AgentConfig,
        message: str,
        history: list[str],
    ) -> str | None:
        if not settings.openai_api_key:
            return None

        try:
            from openai import APIError, APIStatusError, AsyncOpenAI, RateLimitError
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OpenAI SDK is not installed. Run pip install -r backend/requirements.txt.",
            ) from exc

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        input_messages = self._openai_input_messages(agent_config, message, history)
        try:
            response = await client.responses.create(
                model=self._openai_model_name(agent_config),
                instructions=self._openai_instructions(agent_config),
                input=input_messages,
                temperature=agent_config.temperature,
            )
        except (RateLimitError, APIStatusError, APIError):
            return None

        output_text = getattr(response, "output_text", None)
        if output_text and output_text.strip():
            return output_text.strip()
        return None

    def _openai_input_messages(
        self,
        agent_config: AgentConfig,
        message: str,
        history: list[str],
    ) -> list[dict[str, str]]:
        input_messages: list[dict[str, str]] = []
        for item in history[-12:]:
            role, _, content = item.partition(":")
            normalized_role = "assistant" if role.strip() == "assistant" else "user"
            if content.strip():
                input_messages.append(
                    {"role": normalized_role, "content": content.strip()},
                )
        input_messages.append({"role": "user", "content": message})
        return input_messages

    def _openai_instructions(self, agent_config: AgentConfig) -> str:
        return (
            f"{agent_config.system_prompt}\n\n"
            f"Agent name: {agent_config.name}\n"
            f"Agent description: {agent_config.description}\n"
            f"Available tools by name: {', '.join(agent_config.tools) or 'none'}"
        )

    def _openai_model_name(self, agent_config: AgentConfig) -> str:
        model = agent_config.model or settings.default_llm_engine
        if model.startswith("openai:"):
            return model.split(":", 1)[1]
        return model

    def _message_history(
        self,
        messages: list[MessageDocument],
        *,
        current_message: str,
    ) -> list[str]:
        history: list[str] = []
        normalized_current = current_message.strip()
        for index, message in enumerate(messages[-12:]):
            is_current_user_message = (
                index == len(messages[-12:]) - 1
                and message.sender_type == "user"
                and message.content.strip() == normalized_current
            )
            if is_current_user_message:
                continue
            history.append(f"{message.sender_type}: {message.content}")
        return history
