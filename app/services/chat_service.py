import re
from functools import lru_cache

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


@lru_cache(maxsize=1)
def _shared_tool_registry():
    return default_tool_registry()


@lru_cache(maxsize=1)
def _get_openai_client(api_key: str):
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=api_key)


@lru_cache(maxsize=512)
def _infer_tool_names_cached(
    name: str,
    role: str,
    purpose: str,
    template_type: str,
    category_tag: str,
) -> tuple[str, ...]:
    role_text = " ".join([name, role, purpose, template_type, category_tag]).lower()
    tools = ["summarizer"]
    if any(term in role_text for term in ("sales", "lead", "revenue", "marketing")):
        tools.append("sales_playbook")
    if any(term in role_text for term in ("data", "analytics", "report", "metric")):
        tools.append("calculator")
    return tuple(tools)


@lru_cache(maxsize=512)
def _runtime_system_prompt_cached(system_prompt: str, language: str) -> str:
    return (
        f"{system_prompt.strip()}\n\n"
        f"Language rules:\n"
        f"- Default response language is {language}.\n"
        "- Keep the full response in that language unless the user clearly requests another one.\n\n"
        "High-quality response rules:\n"
        "- Answer the user's exact request first; do not introduce yourself or repeat the agent description.\n"
        "- Do not force one fixed template for every answer.\n"
        "- First understand the user's intent, then choose the best response format dynamically.\n"
        "- Choose between plain paragraph, short bullets, numbered steps, headings with sections, table, script, code, analysis, comparison, or troubleshooting flow based on what best fits the request.\n"
        "- For direct/simple questions, answer directly in plain text or short bullets and avoid unnecessary headings.\n"
        "- For explanation or teaching, use sections only if helpful; otherwise use natural paragraphs.\n"
        "- For technical guidance, architecture, roadmap, or analysis, use structured headings and bullets where useful.\n"
        "- For rewriting, chatting, email, proposal, or message-writing tasks, produce a human, natural, ready-to-use answer; do not make it look like a report unless requested.\n"
        "- For code/debugging, explain briefly, then provide code or concrete steps in proper code fences when useful.\n"
        "- If the question is small, keep the answer small. If the question is deep, make the answer detailed.\n"
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
        "- Use clean Markdown with short sections, bullets, tables, or numbered steps only when it improves readability.\n"
        "- Do not always start with headings.\n"
        "- Do not always use bullets.\n"
        "- Use fenced code blocks for code.\n"
        "- Use valid Markdown that renders cleanly with remark-gfm.\n"
        "- Stay in the agent role and focus on the agent purpose."
    )


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

        chats = await self._chats.list_by_agent(user.id or "", agent_id, include_messages=False)
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
        if agent.is_active and agent.status == "enabled":
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This agent is disabled and cannot be used for chat.",
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
        existing_messages = self._sorted_messages(chat.messages)
        user_message = await self._chats.add_message(
            MessageDocument(
                chat_id=chat.id or "",
                agent_id=agent.id or "",
                user_id=chat.user_id,
                sender_type="user",
                role="user",
                content=content,
            ),
        )

        prompt_messages = [*existing_messages, user_message]
        assistant_content = await self._generate_assistant_response(agent, content, prompt_messages)
        assistant_message = await self._chats.add_message(
            MessageDocument(
                chat_id=chat.id or "",
                agent_id=agent.id or "",
                user_id=chat.user_id,
                sender_type="assistant",
                role="assistant",
                content=assistant_content,
            ),
        )

        final_messages = [*prompt_messages, assistant_message]
        title = self._build_chat_title_from_messages(final_messages)
        await self._chats.update_chat_title(chat.id or "", title)
        chat.title = title

        return user_message, assistant_message

    async def _update_user_message_in_chat(
        self,
        agent: AgentDocument,
        chat: ChatDocument,
        message_id: str,
        content: str,
    ) -> tuple[MessageDocument, MessageDocument]:
        message = self._find_message(chat.messages, message_id)
        if message is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
        if message.sender_type != "user":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only user messages can be edited",
            )

        updated_user_message = await self._chats.update_message_content(message.id or "", content)
        if updated_user_message is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        messages = self._sorted_messages(chat.messages)
        updated_messages = [
            updated_user_message if item.id == updated_user_message.id else item
            for item in messages
        ]
        assistant_content = await self._generate_assistant_response(agent, content, updated_messages)
        next_assistant = self._find_next_assistant_message(updated_messages, message.created_at)
        if next_assistant is None:
            assistant_message = await self._chats.add_message(
                MessageDocument(
                    chat_id=chat.id or "",
                    agent_id=agent.id or "",
                    user_id=chat.user_id,
                    sender_type="assistant",
                    role="assistant",
                    content=assistant_content,
                ),
            )
            updated_messages.append(assistant_message)
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
            updated_messages = [
                assistant_message if item.id == assistant_message.id else item
                for item in updated_messages
            ]

        title = self._build_chat_title_from_messages(updated_messages)
        await self._chats.update_chat_title(chat.id or "", title)

        return updated_user_message, assistant_message

    def _build_chat_title(self, content: str) -> str:
        title = " ".join(content.strip().split())
        if len(title) <= 80:
            return title
        return f"{title[:77].rstrip()}..."

    def _build_chat_title_from_messages(self, messages: list[MessageDocument]) -> str:
        first_user_message = next(
            (
                " ".join(message.content.strip().split())
                for message in messages
                if message.sender_type == "user" and message.content.strip()
            ),
            "",
        )
        assistant_message = next(
            (
                " ".join(message.content.strip().split())
                for message in reversed(messages)
                if message.sender_type == "assistant" and message.content.strip()
            ),
            "",
        )
        summary_source = assistant_message or first_user_message
        if assistant_message:
            sentence = re.split(r"(?<=[.!?])\s+", summary_source, maxsplit=1)[0]
            sentence = re.sub(
                r"^(sure|here'?s|below is|this is)\s+",
                "",
                sentence.strip(),
                flags=re.IGNORECASE,
            )
            sentence = sentence.strip(" .:-")
            if len(sentence.split()) >= 2:
                return self._build_chat_title(sentence)
        return self._build_chat_title(first_user_message or "New chat")

    async def _ensure_chat_title(self, chat: ChatDocument) -> None:
        if chat.title:
            return

        messages = self._sorted_messages(chat.messages)
        if not messages and chat.id:
            messages = await self._chats.list_messages(chat.id)
            chat.messages = messages

        first_user_message = next(
            (message for message in messages if message.sender_type == "user"),
            None,
        )
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
            tool_registry=_shared_tool_registry(),
            fallback=self._generate_fallback_response,
        )
        return await platform.run(content, agent_key=runtime_agent.id, history=history)

    def _build_agent_runtime_config(self, agent: AgentDocument) -> AgentConfig:
        return AgentConfig(
            id=agent.id or agent.name,
            name=agent.name,
            role=agent.role,
            description=agent.purpose,
            system_prompt=self._build_runtime_system_prompt(agent),
            tools=agent.tools or self._infer_tool_names(agent),
            model=agent.model or agent.llm_engine or settings.default_llm_engine,
            temperature=agent.temperature,
            is_active=agent.is_active and agent.status == "enabled",
        )

    def _build_runtime_system_prompt(self, agent: AgentDocument) -> str:
        return _runtime_system_prompt_cached(agent.system_prompt, agent.language)

    def _infer_tool_names(self, agent: AgentDocument) -> list[str]:
        return list(
            _infer_tool_names_cached(
                agent.name,
                agent.role,
                agent.purpose,
                agent.template_type or "",
                agent.category_tag or "",
            )
        )

    async def _generate_openai_response(
        self,
        agent_config: AgentConfig,
        message: str,
        history: list[str],
    ) -> str | None:
        if not settings.openai_api_key:
            return None

        try:
            from openai import (
                APIConnectionError,
                APIError,
                APIStatusError,
                RateLimitError,
            )
        except ImportError as exc:
            _ = exc
            return None

        client = _get_openai_client(settings.openai_api_key)
        input_messages = self._openai_input_messages(agent_config, message, history)
        try:
            response = await client.responses.create(
                model=self._openai_model_name(agent_config),
                instructions=self._openai_instructions(agent_config),
                input=input_messages,
                temperature=agent_config.temperature,
            )
        except RateLimitError as exc:
            _ = exc
            return None
        except APIConnectionError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Could not connect to OpenAI from the backend server. Check internet "
                    "access, firewall, or proxy settings."
                ),
            ) from exc
        except APIStatusError as exc:
            detail = getattr(exc, "message", None) or str(exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"OpenAI API returned an error: {detail}",
            ) from exc
        except APIError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"OpenAI API request failed: {exc}",
            ) from exc

        output_text = getattr(response, "output_text", None)
        if output_text and output_text.strip():
            return output_text.strip()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenAI returned an empty response. Try again or use a different model.",
        )

    def _generate_fallback_response(self, agent_config: AgentConfig, message: str) -> str:
        _ = message
        agent_focus = agent_config.description.strip()
        agent_text = " ".join(
            [
                agent_config.name,
                agent_config.role,
                agent_config.description,
            ],
        ).lower()

        if any(
            term in agent_text
            for term in ("health", "medical", "wellness", "doctor", "clinic", "patient")
        ):
            return (
                "I can help organize health questions, explain general wellness information, "
                "prepare symptom notes, and suggest safe next steps to discuss with a qualified "
                "clinician.\n\n"
                "Share the health topic, symptoms, duration, age range, medications, and any "
                "urgent warning signs. If symptoms are severe, sudden, worsening, or involve "
                "chest pain, trouble breathing, fainting, severe bleeding, or confusion, seek "
                "urgent medical care now."
            )

        if any(
            term in agent_text
            for term in ("analytics", "analyst", "analysis", "data", "metric", "report")
        ):
            return (
                "I can help analyze sales performance, define metrics, compare channels, "
                "summarize trends, and turn numbers into clear recommendations.\n\n"
                "To move forward, share the data, time period, metric, segment, or business "
                "question you want answered. For example, I can review conversion rate, revenue "
                "by channel, lead quality, pipeline movement, or campaign performance."
            )

        if any(term in agent_text for term in ("sales", "lead", "revenue", "buyer")):
            return (
                "I can help with sales messaging, lead qualification, product positioning, "
                "objection handling, follow-up scripts, and conversion next steps.\n\n"
                "To move forward, share the product or service, target customer, channel, "
                "and the sales goal. For example, I can draft a buyer reply, improve an offer, "
                "write outreach copy, or build a follow-up plan."
            )

        if any(term in agent_text for term in ("support", "help", "service", "customer")):
            return (
                "Likely next steps:\n"
                "1. Confirm the exact issue, affected account or product, and when it started.\n"
                "2. Check whether this is isolated to one user, one browser, one device, "
                "or all users.\n"
                "3. Try the lowest-risk fix first, such as refreshing the session, "
                "checking settings, or reproducing the issue with a clean login.\n"
                "4. Escalate with screenshots, timestamps, account ID, error text, "
                "and reproduction steps if the issue continues.\n\n"
                "Customer reply draft:\n"
                "Thanks for the details. I am checking the likely cause now. Please send the exact "
                "error text, when it started, and whether it happens on another browser or device "
                "so we can narrow this down quickly."
            )

        return (
            f"Focus: {agent_focus}\n\n"
            "I could not reach the configured LLM provider, so this local fallback is being used. "
            "Review the request, identify the goal, list the missing context, and provide "
            "practical next steps based on the agent's purpose."
        )

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

    def _sorted_messages(self, messages: list[MessageDocument]) -> list[MessageDocument]:
        return sorted(messages, key=lambda message: message.created_at)

    def _find_message(self, messages: list[MessageDocument], message_id: str) -> MessageDocument | None:
        return next((message for message in messages if message.id == message_id), None)

    def _find_next_assistant_message(
        self,
        messages: list[MessageDocument],
        after_created_at,
    ) -> MessageDocument | None:
        for message in self._sorted_messages(messages):
            if message.sender_type == "assistant" and message.created_at > after_created_at:
                return message
        return None
