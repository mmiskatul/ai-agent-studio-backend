import json
import re
from datetime import timedelta
from functools import lru_cache
from logging import getLogger
from pathlib import Path
from time import perf_counter

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.agents.config import AgentConfig
from app.agents.configs import DEFAULT_AGENT_CONFIGS
from app.agents.factory import create_agent
from app.agents.routing import AgentRouter
from app.agents.state import runtime_agent_registry
from app.core.config import settings
from app.models.agent import AgentDocument
from app.models.base import now_utc
from app.models.chat import ChatDocument, ChatMemoryDocument, MessageDocument
from app.models.user import UserDocument
from app.repositories.agent_repository import AgentRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.agent import (
    AgentAICreate,
    AgentBuilderCreate,
    AgentCreate,
    AgentDescriptionGenerateRequest,
    AgentConfigResponse,
    AgentRegistryRebuildResponse,
    AgentRouteResponse,
    AgentResponse,
    AgentSystemPromptGenerateRequest,
    AgentUpdate,
    AgentWelcomeMessageGenerateRequest,
    MemorySummary,
)
from app.services.agent_response_prompt import (
    AgentResponsePromptBuilder,
    parse_agent_json_response,
)
from app.tools.registry import default_tool_registry

logger = getLogger(__name__)
MESSAGE_WINDOW_SIZE = 100
MAX_AGENT_KNOWLEDGE_CHARS = 30000


@lru_cache(maxsize=1)
def _get_openai_client(api_key: str):
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=api_key)


@lru_cache(maxsize=512)
def _infer_tools_cached(
    name: str,
    role: str,
    purpose: str,
    template_type: str,
    category_tag: str,
) -> tuple[str, ...]:
    lowered_text = " ".join([name, role, purpose, template_type, category_tag]).lower()
    tools = ["summarizer"]
    if any(term in lowered_text for term in ("sales", "lead", "revenue", "marketing")):
        tools.append("sales_playbook")
    if any(term in lowered_text for term in ("data", "analytics", "report", "metric")):
        tools.append("calculator")
    if any(term in lowered_text for term in ("search", "research", "web")):
        tools.append("search")
    return tuple(tools)


class AgentService:
    def __init__(
        self,
        agents: AgentRepository,
        chats: ChatRepository,
        messages: MessageRepository | None = None,
    ) -> None:
        self._agents = agents
        self._chats = chats
        self._messages = messages
        self._response_prompt_builder = AgentResponsePromptBuilder()

    def parse_memory_summary(self, value: object) -> MemorySummary:
        memory = self._parse_chat_memory(value)
        return MemorySummary(
            title=memory.title.strip(),
            description=memory.running_summary.strip(),
        )

    def _parse_chat_memory(self, value: object, legacy_summary: str | None = None) -> ChatMemoryDocument:
        if isinstance(value, ChatMemoryDocument):
            return value

        if isinstance(value, dict):
            try:
                return ChatMemoryDocument.model_validate(value)
            except ValidationError:
                pass

        summary_source = legacy_summary
        if isinstance(value, str):
            summary_source = value

        if summary_source and summary_source.strip():
            trimmed_summary = summary_source.strip()
            if trimmed_summary.startswith("{"):
                try:
                    parsed = json.loads(trimmed_summary)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    title = parsed.get("title")
                    description = parsed.get("description")
                    return ChatMemoryDocument(
                        title=title.strip() if isinstance(title, str) else "",
                        running_summary=description.strip() if isinstance(description, str) else "",
                    )
            return ChatMemoryDocument(running_summary=trimmed_summary)

        return ChatMemoryDocument()

    def _memory_context_text(self, memory: ChatMemoryDocument) -> str:
        summary_parts = []
        if memory.title:
            summary_parts.append(f"Title: {memory.title}")
        if memory.running_summary:
            summary_parts.append(f"Running Summary: {memory.running_summary}")
        if memory.last_user_goal:
            summary_parts.append(f"Last User Goal: {memory.last_user_goal}")
        if memory.recent_topics:
            summary_parts.append("Recent Topics: " + ", ".join(memory.recent_topics))
        if memory.preferences:
            summary_parts.append("Preferences: " + "; ".join(memory.preferences))
        if memory.open_loops:
            summary_parts.append("Open Loops: " + "; ".join(memory.open_loops))
        return "\n".join(summary_parts).strip()

    def _log_timed_operation(self, operation: str, started_at: float, **extra: object) -> None:
        if not settings.request_timing_enabled:
            return
        duration_ms = (perf_counter() - started_at) * 1000
        log_level = logger.warning if duration_ms >= settings.request_slow_log_ms else logger.info
        extra_text = " ".join(f"{key}={value}" for key, value in extra.items() if value is not None)
        suffix = f" {extra_text}" if extra_text else ""
        log_level("service_timing operation=%s duration_ms=%.2f%s", operation, duration_ms, suffix)

    async def list_agents(self, user: UserDocument) -> list[AgentResponse]:
        user_id = user.id or ""
        agents = await self._agents.list_by_user(user_id)
        query_counts = await self._safe_count_queries_30d_by_agent(user_id)
        responses: list[AgentResponse] = []
        for agent in agents:
            try:
                responses.append(
                    self._agent_response(agent, queries_30d=query_counts.get(agent.id or "", 0))
                )
            except ValidationError:
                logger.exception("Skipping invalid agent document during list_agents", extra={"agent_id": agent.id})
        return responses

    async def get_agent(self, agent_id: str, user: UserDocument) -> AgentResponse:
        agent = await self._get_agent_document(agent_id, user)
        query_counts = await self._safe_count_queries_30d_by_agent(user.id or "", [agent.id or ""])
        return self._agent_response(agent, queries_30d=query_counts.get(agent.id or "", 0))

    async def list_agent_configs(self, user: UserDocument) -> list[AgentConfigResponse]:
        agents = await self._agents.list_by_user(user.id or "")
        return [
            AgentConfigResponse.model_validate(self._agent_config(agent).model_dump())
            for agent in agents
        ]

    async def rebuild_registry(self, user: UserDocument) -> AgentRegistryRebuildResponse:
        agents = await self._agents.list_by_user(user.id or "")
        tool_registry = default_tool_registry()
        runtime_agent_registry.clear()

        registered_ids: list[str] = []
        active_count = 0
        for agent in agents:
            config = self._agent_config(agent)
            if not config.is_active:
                continue
            active_count += 1
            runtime_agent_registry.register(create_agent(config, tool_registry))
            registered_ids.append(config.id)

        if not agents and not registered_ids:
            for config in DEFAULT_AGENT_CONFIGS:
                runtime_agent_registry.register(create_agent(config, tool_registry))
                registered_ids.append(config.id)
                if config.is_active:
                    active_count += 1

        return AgentRegistryRebuildResponse(
            total_agents=len(registered_ids),
            active_agents=active_count,
            agent_ids=registered_ids,
        )

    async def seed_default_agents(self, user: UserDocument) -> list[AgentResponse]:
        existing_agents = await self._agents.list_by_user(user.id or "")
        existing_names = {agent.name.lower() for agent in existing_agents}
        created: list[AgentDocument] = []

        for config in DEFAULT_AGENT_CONFIGS:
            if config.name.lower() in existing_names:
                continue
            agent = AgentDocument(
                user_id=user.id or "",
                name=config.name,
                role=config.name,
                purpose=config.description,
                description=config.description,
                system_prompt=config.system_prompt,
                llm_engine=config.model,
                model=config.model,
                temperature=config.temperature,
                status="enabled" if config.is_active else "disabled",
                tools=config.tools,
                is_active=config.is_active,
            )
            created.append(await self._agents.create(agent))

        return [self._agent_response(agent) for agent in created]

    async def route_agent(
        self,
        user: UserDocument,
        task: str,
        agent_key: str | None = None,
    ) -> AgentRouteResponse:
        await self.rebuild_registry(user)
        try:
            agent = AgentRouter(runtime_agent_registry).select(task, agent_key=agent_key)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active agent is available for this task.",
            ) from exc
        return AgentRouteResponse(
            agent_id=agent.config.id,
            agent_name=agent.config.name,
            description=agent.config.description,
            tools=agent.config.tools,
        )

    async def generate_agent_response(
        self,
        agent_id: str,
        user: UserDocument,
        content: str,
        chat_id: str | None = None,
        attachment_text: str | None = None,
        attachment_name: str | None = None,
    ) -> tuple[AgentDocument, ChatDocument, str, ChatMemoryDocument]:
        agent = await self._get_agent_document(agent_id, user)
        config = self._agent_config(agent)
        if not config.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This agent is disabled and cannot generate responses.",
            )

        prepared_content = self._prepare_user_message_content(content, attachment_name)
        chat = await self._get_or_create_memory_chat(agent, user, prepared_content, chat_id=chat_id)
        existing_messages = self._sorted_messages(chat.messages)
        user_message = await self._chats.add_message(
            MessageDocument(
                chat_id=chat.id or "",
                agent_id=agent.id or "",
                user_id=user.id or "",
                sender_type="user",
                role="user",
                content=prepared_content,
            ),
        )
        messages = [*existing_messages, user_message]
        response = await self._generate_memory_response(
            agent=agent,
            config=config,
            chat=chat,
            current_message=user_message,
            messages=messages,
            attachment_text=attachment_text,
            attachment_name=attachment_name,
        )
        parsed_response = parse_agent_json_response(response)
        assistant_message = await self._chats.add_message(
            MessageDocument(
                chat_id=chat.id or "",
                agent_id=agent.id or "",
                user_id=user.id or "",
                sender_type="assistant",
                role="assistant",
                content=parsed_response.response,
            ),
        )
        memory = self._build_chat_memory(
            previous_memory=self._parse_chat_memory(chat.memory, chat.summary),
            system_summary=parsed_response.system_summary,
            messages=[*messages, assistant_message],
        )
        await self._chats.update_chat_memory(chat.id or "", memory)
        chat.memory = memory
        chat.summary = None
        await self._apply_memory_title(chat, memory)
        return agent, chat, parsed_response.response, memory

    async def get_agent_response_history(
        self,
        agent_id: str,
        user: UserDocument,
        chat_id: str | None = None,
    ) -> tuple[AgentDocument, ChatDocument | None, list[MessageDocument], int]:
        agent = await self._get_agent_document(agent_id, user)
        chat = (
            await self._chats.get_owned_chat(user.id or "", agent.id or "", chat_id, include_messages=False)
            if chat_id
            else await self._chats.get_for_agent(user.id or "", agent.id or "", include_messages=False)
        )
        if chat is None:
            return agent, None, [], 0
        total_count = (await self._chats.count_messages_by_chat_ids([chat.id or ""])).get(chat.id or "", 0)
        messages = await self._chats.list_messages(chat.id or "", limit=MESSAGE_WINDOW_SIZE)
        return agent, chat, messages, total_count

    async def list_agent_response_pages(
        self,
        agent_id: str,
        user: UserDocument,
    ) -> list[tuple[ChatDocument, int]]:
        agent = await self._get_agent_document(agent_id, user)
        chats = await self._chats.list_by_agent(user.id or "", agent.id or "", include_messages=False)
        message_counts = await self._chats.count_messages_by_chat_ids(
            [chat.id or "" for chat in chats if chat.id],
        )
        return [(chat, message_counts.get(chat.id or "", 0)) for chat in chats]

    async def list_all_agent_response_pages(
        self,
        user: UserDocument,
    ) -> list[tuple[ChatDocument, int]]:
        chats = await self._chats.list_by_user(user.id or "", include_messages=False)
        message_counts = await self._chats.count_messages_by_chat_ids(
            [chat.id or "" for chat in chats if chat.id],
        )
        agent_summaries = await self._agents.list_summaries_by_user(user.id or "")
        agent_names = {
            str(agent.get("_id")): agent.get("name")
            for agent in agent_summaries
            if agent.get("_id") and isinstance(agent.get("name"), str)
        }

        for chat in chats:
            if not chat.agent_name:
                chat.agent_name = agent_names.get(chat.agent_id)

        return [(chat, message_counts.get(chat.id or "", 0)) for chat in chats]

    async def create_agent_response_page(
        self,
        agent_id: str,
        user: UserDocument,
        title: str | None = None,
    ) -> ChatDocument:
        agent = await self._get_agent_document(agent_id, user)
        config = self._agent_config(agent)
        if not config.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This agent is disabled and cannot create response pages.",
            )
        return await self._chats.create(
            ChatDocument(
                user_id=user.id or "",
                agent_id=agent.id or "",
                title=title.strip() if title and title.strip() else "New chat",
            ),
        )

    async def get_latest_agent_response_history(
        self,
        user: UserDocument,
    ) -> tuple[AgentDocument, ChatDocument, list[MessageDocument]]:
        chat = await self._chats.get_latest_for_user(user.id or "")
        if chat is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

        agent = await self._get_agent_document(chat.agent_id, user)
        return agent, chat, self._sorted_messages(chat.messages)

    async def update_agent_response_message(
        self,
        agent_id: str,
        user: UserDocument,
        message_id: str,
        content: str,
    ) -> tuple[AgentDocument, ChatDocument, list[MessageDocument]]:
        agent = await self._get_agent_document(agent_id, user)
        config = self._agent_config(agent)
        if not config.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This agent is disabled and cannot generate responses.",
            )

        chat, message = await self._get_owned_response_message(agent, user, message_id)
        if message.sender_type != "user":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only user messages can be edited.",
            )

        updated_user_message = await self._chats.update_message_content(message.id or "", content)
        if updated_user_message is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        next_assistant = self._find_next_assistant_message(chat.messages, message.created_at)
        messages = self._sorted_messages(chat.messages)
        messages = [
            updated_user_message if item.id == updated_user_message.id else item
            for item in messages
        ]
        prompt_messages = [
            item for item in messages if next_assistant is None or item.id != next_assistant.id
        ]
        response = await self._generate_memory_response(
            agent=agent,
            config=config,
            chat=chat,
            current_message=updated_user_message,
            messages=prompt_messages,
        )
        parsed_response = parse_agent_json_response(response)

        if next_assistant is None:
            assistant_message = await self._chats.add_message(
                MessageDocument(
                    chat_id=chat.id or "",
                    sender_type="assistant",
                    content=parsed_response.response,
                ),
            )
            messages = [*messages, assistant_message]
        else:
            updated_assistant = await self._chats.update_message_content(
                next_assistant.id or "",
                parsed_response.response,
            )
            if updated_assistant is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Message not found",
                )
            messages = [
                updated_assistant if item.id == updated_assistant.id else item
                for item in messages
            ]

        memory = self._build_chat_memory(
            previous_memory=self._parse_chat_memory(chat.memory, chat.summary),
            system_summary=parsed_response.system_summary,
            messages=messages,
        )
        await self._chats.update_chat_memory(chat.id or "", memory)
        chat.memory = memory
        chat.summary = None
        await self._apply_memory_title(chat, memory)
        return agent, chat, messages

    async def delete_agent_response_message(
        self,
        agent_id: str,
        user: UserDocument,
        message_id: str,
    ) -> tuple[AgentDocument, ChatDocument, list[MessageDocument]]:
        agent = await self._get_agent_document(agent_id, user)
        config = self._agent_config(agent)
        if not config.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This agent is disabled and cannot generate responses.",
            )

        chat, message = await self._get_owned_response_message(agent, user, message_id)
        paired_assistant = None
        if message.sender_type == "user":
            paired_assistant = self._find_next_assistant_message(chat.messages, message.created_at)

        deleted = await self._chats.delete_message(message.id or "")
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        if paired_assistant is not None:
            await self._chats.delete_message(paired_assistant.id or "")

        messages = [
            item
            for item in self._sorted_messages(chat.messages)
            if item.id != message.id and (paired_assistant is None or item.id != paired_assistant.id)
        ]
        memory = self._build_chat_memory(
            previous_memory=self._parse_chat_memory(chat.memory, chat.summary),
            system_summary="Deleted a message and rebuilt memory from remaining chat history.",
            messages=messages,
        )
        await self._chats.update_chat_memory(chat.id or "", memory)
        chat.memory = memory
        chat.summary = None
        await self._apply_memory_title(chat, memory)
        return agent, chat, messages

    async def _get_or_create_memory_chat(
        self,
        agent: AgentDocument,
        user: UserDocument,
        content: str,
        chat_id: str | None = None,
    ) -> ChatDocument:
        if chat_id:
            chat = await self._chats.get_owned_chat(user.id or "", agent.id or "", chat_id)
            if chat is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
            return chat

        existing = await self._chats.get_for_agent(user.id or "", agent.id or "")
        if existing is not None:
            return existing

        return await self._chats.create(
            ChatDocument(
                user_id=user.id or "",
                agent_id=agent.id or "",
                title="New page",
            ),
        )

    async def _get_memory_chat(self, agent: AgentDocument, user: UserDocument) -> ChatDocument:
        chat = await self._chats.get_for_agent(user.id or "", agent.id or "")
        if chat is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
        return chat

    async def _get_owned_response_message(
        self,
        agent: AgentDocument,
        user: UserDocument,
        message_id: str,
    ) -> tuple[ChatDocument, MessageDocument]:
        chat = await self._chats.get_owned_chat_by_message(user.id or "", agent.id or "", message_id)
        if chat is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
        message = next((item for item in chat.messages if item.id == message_id), None)
        if message is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
        return chat, message

    async def _get_owned_message(
        self,
        chat: ChatDocument,
        message_id: str,
    ) -> MessageDocument:
        message = await self._chats.get_message(message_id)
        if message is None or message.chat_id != (chat.id or ""):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
        return message

    def _sorted_messages(self, messages: list[MessageDocument]) -> list[MessageDocument]:
        return sorted(messages, key=lambda message: message.created_at)

    def _find_next_assistant_message(
        self,
        messages: list[MessageDocument],
        after_created_at,
    ) -> MessageDocument | None:
        for message in self._sorted_messages(messages):
            if message.sender_type == "assistant" and message.created_at > after_created_at:
                return message
        return None

    def _build_title(self, content: str) -> str:
        title = " ".join(content.strip().split())
        if len(title) <= 80:
            return title
        return f"{title[:77].rstrip()}..."

    def _build_summary_title(self, content: str) -> str:
        title = " ".join(content.strip().split())
        if not title:
            return ""

        title = re.sub(
            r"^(the\s+)?user\s+(asked|requested|wants|needs|is asking|asked for)\s+(for|to|about)?\s*",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(
            r"^(agent|assistant|bot|system)\s+(handled|answered|responded to)\s*",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(
            r"\s+(using|with|based on|from stored|from previous|while using)\s+.*$",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.split(r"(?<=[.!?])\s+", title, maxsplit=1)[0]
        title = title.strip(" .:-")

        if not title or len(title.split()) < 2:
            return ""
        if len(title) <= 72:
            return title
        return f"{title[:69].rstrip()}..."

    def _is_weak_title_source(self, content: str) -> bool:
        normalized = " ".join(content.strip().lower().split())
        if not normalized:
            return True
        if normalized in {
            "hi",
            "hello",
            "hey",
            "hii",
            "test",
            "ok",
            "okay",
            "thanks",
            "thank you",
        }:
            return True
        return len(normalized.split()) < 3 and len(normalized) < 18

    def _build_assistant_title(self, messages: list[MessageDocument]) -> str:
        assistant_message = next(
            (
                message.content.strip()
                for message in reversed(messages)
                if message.sender_type == "assistant" and message.content.strip()
            ),
            "",
        )
        if not assistant_message:
            return ""

        lines = [line.strip(" #*-0123456789.\t") for line in assistant_message.splitlines()]
        candidates = [line for line in lines if line and len(line.split()) >= 3]
        source = candidates[0] if candidates else assistant_message
        source = re.sub(
            r"^(here'?s|here is|below is|this is|sure,?)\s+(a|an|the)?\s*",
            "",
            source.strip(),
            flags=re.IGNORECASE,
        )
        source = re.sub(r"^brief\s+", "", source, flags=re.IGNORECASE)
        source = re.split(r"(?<=[.!?:])\s+", source, maxsplit=1)[0]
        source = source.strip(" .:-")
        if self._is_weak_title_source(source):
            return ""
        return self._build_title(source)

    def _build_memory_title(
        self,
        *,
        previous_memory: ChatMemoryDocument,
        system_summary: str,
        messages: list[MessageDocument],
    ) -> str:
        if system_summary.strip():
            summary_title = self._build_summary_title(system_summary)
            if summary_title and not self._is_weak_title_source(summary_title):
                return summary_title

        assistant_title = self._build_assistant_title(messages)
        if assistant_title:
            return assistant_title

        first_user_message = next(
            (
                " ".join(message.content.strip().split())
                for message in messages
                if message.sender_type == "user" and message.content.strip()
            ),
            "",
        )
        if first_user_message and not self._is_weak_title_source(first_user_message):
            return self._build_title(first_user_message)

        latest_user_message = next(
            (
                " ".join(message.content.strip().split())
                for message in reversed(messages)
                if message.sender_type == "user" and message.content.strip()
            ),
            "",
        )
        if latest_user_message and not self._is_weak_title_source(latest_user_message):
            return self._build_title(latest_user_message)

        if previous_memory.title.strip():
            return previous_memory.title.strip()
        return "New memory"

    async def _apply_memory_title(self, chat: ChatDocument, memory: ChatMemoryDocument) -> None:
        next_title = memory.title.strip()
        if not next_title or not chat.id:
            return
        await self._chats.update_chat_title(chat.id, next_title)
        chat.title = next_title

    async def _generate_memory_response(
        self,
        *,
        agent: AgentDocument,
        config: AgentConfig,
        chat: ChatDocument,
        current_message: MessageDocument,
        messages: list[MessageDocument],
        attachment_text: str | None = None,
        attachment_name: str | None = None,
    ) -> str:
        memory = self._parse_chat_memory(chat.memory, chat.summary)
        prompt = self._response_prompt_builder.build(
            agent=agent,
            config=config,
            memory=memory,
            current_message=current_message.content,
            messages=messages,
            attachment_text=attachment_text,
            attachment_name=attachment_name,
        )
        if not settings.openai_api_key:
            return self._fallback_agent_response(
                config,
                current_message.content,
                self._memory_context_text(memory),
            )

        try:
            from openai import (
                APIConnectionError,
                APIError,
                APIStatusError,
                RateLimitError,
            )
        except ImportError:
            return self._fallback_agent_response(
                config,
                current_message.content,
                self._memory_context_text(memory),
            )

        client = _get_openai_client(settings.openai_api_key)
        started_at = perf_counter()
        try:
            response = await client.responses.create(
                model=config.model or settings.default_llm_engine,
                instructions=self._response_prompt_builder.json_instructions,
                input=prompt,
                temperature=config.temperature,
            )
        except (APIConnectionError, APIError, APIStatusError, RateLimitError):
            self._log_timed_operation(
                "generate_memory_response.openai_error",
                started_at,
                agent_id=agent.id or "",
                model=config.model or settings.default_llm_engine,
            )
            return self._fallback_agent_response(
                config,
                current_message.content,
                self._memory_context_text(memory),
            )
        self._log_timed_operation(
            "generate_memory_response.openai",
            started_at,
            agent_id=agent.id or "",
            model=config.model or settings.default_llm_engine,
        )

        output_text = getattr(response, "output_text", None)
        if output_text and output_text.strip():
            return output_text.strip()
        return self._fallback_agent_response(
            config,
            current_message.content,
            self._memory_context_text(memory),
        )

    def _prepare_user_message_content(self, content: str, attachment_name: str | None = None) -> str:
        normalized_content = content.strip()
        normalized_attachment_name = (
            attachment_name.strip() if isinstance(attachment_name, str) and attachment_name.strip() else ""
        )
        if normalized_content and normalized_attachment_name:
            return f"{normalized_content}\n\n[Attached file: {normalized_attachment_name}]"
        if normalized_content:
            return normalized_content
        if normalized_attachment_name:
            return f"[Attached file: {normalized_attachment_name}]"
        return "Please review the attached file."

    def _build_chat_memory(
        self,
        *,
        previous_memory: ChatMemoryDocument,
        system_summary: str,
        messages: list[MessageDocument],
    ) -> ChatMemoryDocument:
        recent_user_messages = [
            " ".join(message.content.strip().split())
            for message in messages
            if message.sender_type == "user" and message.content.strip()
        ]
        latest_user_goal = recent_user_messages[-1] if recent_user_messages else previous_memory.last_user_goal
        running_summary = system_summary.strip() or previous_memory.running_summary.strip()
        if len(running_summary) > 1200:
            running_summary = running_summary[:1200].rstrip()

        recent_topics = self._collect_recent_topics(recent_user_messages, previous_memory.recent_topics)
        preferences = self._merge_memory_items(
            previous_memory.preferences,
            self._extract_preferences(recent_user_messages),
            limit=6,
        )
        open_loops = self._merge_memory_items(
            previous_memory.open_loops,
            self._extract_open_loops(messages),
            limit=6,
        )
        facts = self._merge_memory_items(
            previous_memory.facts,
            [system_summary.strip()] if system_summary.strip() else [],
            limit=6,
        )

        return ChatMemoryDocument(
            title=self._build_memory_title(
                previous_memory=previous_memory,
                system_summary=system_summary,
                messages=messages,
            ),
            running_summary=running_summary,
            facts=facts,
            preferences=preferences,
            open_loops=open_loops,
            recent_topics=recent_topics,
            last_user_goal=latest_user_goal,
            last_updated_at=now_utc(),
        )

    def _fallback_agent_response(
        self,
        config: AgentConfig,
        message: str,
        memory_summary: str,
    ) -> str:
        _ = memory_summary
        cleaned_message = " ".join(message.strip().split())
        lowered_message = cleaned_message.lower()
        context = config.description.strip() or config.role.strip() or config.name.strip()
        agent_text = " ".join(
            [
                config.name,
                config.role,
                config.description,
            ]
        ).lower()

        if not cleaned_message:
            return (
                f"I can help with {context}.\n\n"
                "Tell me the exact result you want, and I will respond directly."
            )

        if any(term in lowered_message for term in ("hi", "hello", "hey", "bro")) and len(cleaned_message) <= 20:
            if any(term in agent_text for term in ("sales", "lead", "buyer", "revenue")):
                return (
                    "Hi. I can help with buyer replies, outreach copy, offers, lead qualification, "
                    "and follow-up strategy.\n\n"
                    "Tell me what you want to do next: draft a message, improve a pitch, qualify a lead, or plan follow-up."
                )
            return (
                f"Hi. I can help with {context}.\n\n"
                "Tell me what you want to do next, and I will answer directly."
            )

        if any(term in lowered_message for term in ("write", "draft", "reply", "message", "email")):
            if any(term in agent_text for term in ("sales", "lead", "buyer", "revenue")):
                return (
                    "I can write that for you.\n\n"
                    "Send me these details:\n"
                    "- product or service\n"
                    "- target customer\n"
                    "- channel (email, WhatsApp, LinkedIn, call follow-up)\n"
                    "- goal of the message\n"
                    "- tone you want\n\n"
                    "If you want, paste the buyer's message and I will draft the reply."
                )
            return (
                "I can draft that.\n\n"
                "Send me the target audience, purpose, tone, and any important details, and I will write the final version."
            )

        if any(term in lowered_message for term in ("what is", "what's", "why", "explain", "meaning")):
            return (
                f"Direct answer: {cleaned_message}.\n\n"
                "Send the exact context, and I will turn this into a specific business-ready explanation."
            )

        if len(cleaned_message) <= 120 and any(
            term in lowered_message for term in ("sell", "sales", "lead", "customer", "buyer", "price", "offer")
        ):
            return (
                "Here is the direct way to approach this:\n\n"
                "1. Identify the buyer and the stage of the conversation.\n"
                "2. Clarify the offer, price point, or objection.\n"
                "3. Give one clear next action.\n\n"
                "If you send the exact buyer message or sales situation, I will turn this into a specific reply or plan."
            )

        if len(cleaned_message) <= 120 and any(
            term in lowered_message for term in ("problem", "issue", "error", "bug", "not working", "fix")
        ):
            return (
                "Send the exact issue, what you expected, and what happened instead.\n\n"
                "I will give you the likely cause and the next fix steps."
            )

        if any(term in lowered_message for term in ("plan", "strategy", "steps", "how", "improve")):
            if any(term in agent_text for term in ("sales", "lead", "buyer", "revenue")):
                return (
                    "Here is a direct sales structure to move forward:\n\n"
                    "1. Define the buyer and current stage.\n"
                    "2. Clarify the offer and strongest value point.\n"
                    "3. Handle the main objection or friction.\n"
                    "4. Give one clear next action.\n"
                    "5. Follow up with a short reminder and proof point.\n\n"
                    "If you share the product, customer type, and goal, I can turn this into a specific sales plan."
                )
            return (
                "I can break that down into direct steps.\n\n"
                "Share the goal, current situation, and constraint, and I will give you a specific plan."
            )

        if any(term in lowered_message for term in ("can you help", "help me", "need help")):
            if any(term in agent_text for term in ("sales", "lead", "buyer", "revenue")):
                return (
                    "Yes. I can help with the sales side directly.\n\n"
                    "Best next move:\n"
                    "- if you have a buyer message, paste it and I will draft the reply\n"
                    "- if you have an offer problem, describe it and I will improve the positioning\n"
                    "- if you have a lead, share the details and I will help qualify it"
                )
            return (
                "Yes. Send the exact task, example, or message you want worked on, and I will respond with the actual output."
            )

        if any(term in agent_text for term in ("sales", "lead", "buyer", "revenue")):
            return (
                "I can help with the actual sales work: buyer replies, offer positioning, lead qualification, objection handling, and follow-up.\n\n"
                "Send the specific sales situation and I will answer it directly."
            )

        if any(term in agent_text for term in ("support", "service", "customer")):
            return (
                "Send the exact problem, affected product or account, and any error text.\n\n"
                "I will respond with the diagnosis, next steps, and the customer-facing reply if needed."
            )

        return (
            f"Send the exact result you want for this request.\n\n"
            f"I will respond directly based on {context}, with a specific answer instead of a general description."
        )

    def _collect_recent_topics(
        self,
        recent_user_messages: list[str],
        previous_topics: list[str],
    ) -> list[str]:
        collected: list[str] = []
        for message in [*previous_topics, *recent_user_messages[-5:]]:
            topic = self._build_title(message).strip()
            if topic and topic.lower() not in {item.lower() for item in collected}:
                collected.append(topic)
        return collected[-5:]

    def _extract_preferences(self, recent_user_messages: list[str]) -> list[str]:
        preferences: list[str] = []
        markers = ("prefer", "please", "do not", "don't", "use ", "avoid ")
        for message in recent_user_messages[-6:]:
            lowered_message = message.lower()
            if any(marker in lowered_message for marker in markers):
                preferences.append(message)
        return preferences[-4:]

    def _extract_open_loops(self, messages: list[MessageDocument]) -> list[str]:
        open_loops: list[str] = []
        for message in messages[-6:]:
            if message.sender_type == "user" and "?" in message.content:
                open_loops.append(" ".join(message.content.strip().split()))
        return open_loops[-4:]

    def _merge_memory_items(
        self,
        existing: list[str],
        new_items: list[str],
        *,
        limit: int,
    ) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for item in [*existing, *new_items]:
            normalized = " ".join(item.strip().split())
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(normalized)
        return merged[-limit:]

    async def _get_agent_document(self, agent_id: str, user: UserDocument) -> AgentDocument:
        agent = await self._agents.get_owned(agent_id, user.id or "")
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        return agent

    async def create_agent(self, payload: AgentCreate, user: UserDocument) -> AgentResponse:
        data = self._normalize_agent_config(payload.model_dump(by_alias=False))
        agent = AgentDocument(user_id=user.id or "", **data)
        return self._agent_response(await self._agents.create(agent))

    async def create_builder_agent(
        self,
        payload: AgentBuilderCreate,
        user: UserDocument,
    ) -> AgentResponse:
        normalized_status = self._normalize_status(payload.status)
        agent = AgentDocument(
            user_id=user.id or "",
            name=payload.name,
            role=payload.category_tag or payload.base_template or "AgentLab",
            purpose=payload.short_description,
            description=payload.short_description,
            language=self._normalize_language(payload.language),
            template_type=payload.base_template,
            template_id=payload.template_id,
            category_tag=payload.category_tag,
            system_prompt=payload.system_prompt,
            welcome_message=payload.welcome_message,
            llm_engine=payload.llm_engine,
            model=payload.llm_engine,
            temperature=payload.temperature,
            status=normalized_status,
            tools=self._infer_tools(payload.category_tag or payload.base_template),
            is_active=normalized_status == "enabled",
        )
        return self._agent_response(await self._agents.create(agent))

    async def create_ai_agent(self, payload: AgentAICreate, user: UserDocument) -> AgentResponse:
        system_prompt = await self._generate_system_prompt(payload)
        normalized_status = self._normalize_status(payload.status)
        agent = AgentDocument(
            user_id=user.id or "",
            name=payload.name,
            role=payload.role or "AI Agent",
            purpose=payload.purpose,
            description=payload.purpose,
            language=self._normalize_language(payload.language),
            template_type=payload.template_type,
            template_id=payload.template_id,
            category_tag=payload.template_type,
            system_prompt=system_prompt,
            llm_engine=settings.default_llm_engine,
            model=settings.default_llm_engine,
            status=normalized_status,
            tools=self._infer_tools(payload.role or payload.template_type),
            is_active=normalized_status == "enabled",
        )
        return self._agent_response(await self._agents.create(agent))

    async def _count_queries_30d_by_agent(
        self,
        user_id: str,
        agent_ids: list[str] | None = None,
    ) -> dict[str, int]:
        chats = await self._chats.list_by_user(user_id, include_messages=False)
        if agent_ids is not None:
            allowed_agent_ids = set(agent_ids)
            chats = [chat for chat in chats if chat.agent_id in allowed_agent_ids]

        chat_ids = [chat.id or "" for chat in chats if chat.id]
        chat_agent_map = {chat.id or "": chat.agent_id for chat in chats if chat.id}
        query_counts_by_chat = await self._chats.count_user_messages_by_chat_ids(
            chat_ids,
            since=now_utc() - timedelta(days=30),
        )

        query_counts_by_agent: dict[str, int] = {}
        for chat_id, count in query_counts_by_chat.items():
            agent_id = chat_agent_map.get(chat_id)
            if agent_id:
                query_counts_by_agent[agent_id] = query_counts_by_agent.get(agent_id, 0) + count

        if self._messages is not None:
            message_counts_by_agent = await self._messages.count_user_messages_by_agent(
                user_id,
                since=now_utc() - timedelta(days=30),
                agent_ids=agent_ids,
            )
            for agent_id, count in message_counts_by_agent.items():
                query_counts_by_agent[agent_id] = query_counts_by_agent.get(agent_id, 0) + count
        return query_counts_by_agent

    async def _safe_count_queries_30d_by_agent(
        self,
        user_id: str,
        agent_ids: list[str] | None = None,
    ) -> dict[str, int]:
        try:
            return await self._count_queries_30d_by_agent(user_id, agent_ids)
        except Exception:
            logger.exception(
                "Falling back to zero query counts due to count failure",
                extra={"user_id": user_id, "agent_ids": agent_ids},
            )
            return {}

    def _agent_response(self, agent: AgentDocument, queries_30d: int = 0) -> AgentResponse:
        normalized_status = self._normalize_status(agent.status)
        return AgentResponse.model_validate(
            {
                **agent.model_dump(),
                "id": agent.id or "",
                "status": normalized_status,
                "description": agent.description or agent.purpose,
                "model": agent.model or agent.llm_engine,
                "owner_user_id": agent.user_id,
                "is_active": agent.is_active and normalized_status == "enabled",
                "queries_30d": queries_30d,
            },
        )

    def _agent_config(self, agent: AgentDocument) -> AgentConfig:
        normalized_status = self._normalize_status(agent.status)
        return AgentConfig(
            id=agent.id or agent.name,
            name=agent.name,
            role=agent.role,
            description=agent.description or agent.purpose,
            system_prompt=agent.system_prompt,
            tools=agent.tools or self._infer_tools(
                " ".join(
                    [
                        agent.name,
                        agent.role,
                        agent.purpose,
                        agent.template_type or "",
                        agent.category_tag or "",
                    ],
                ),
            ),
            model=agent.model or agent.llm_engine or settings.default_llm_engine,
            temperature=agent.temperature,
            is_active=agent.is_active and normalized_status == "enabled",
        )

    def _normalize_agent_config(self, data: dict) -> dict:
        data["description"] = data.get("description") or data.get("purpose") or data.get("role")
        if "knowledge_text" in data and isinstance(data["knowledge_text"], str):
            data["knowledge_text"] = self._normalize_knowledge_text(data["knowledge_text"])
        data["model"] = data.get("model") or data.get("llm_engine") or settings.default_llm_engine
        data["llm_engine"] = data.get("llm_engine") or data["model"]
        data["status"] = self._normalize_status(data.get("status"))
        data["language"] = self._normalize_language(data.get("language"))
        data["tools"] = data.get("tools") or self._infer_tools(
            " ".join(
                str(value)
                for value in (
                    data.get("name", ""),
                    data.get("role", ""),
                    data.get("purpose", ""),
                    data.get("template_type", ""),
                    data.get("category_tag", ""),
                )
            ),
        )
        data["is_active"] = data.get("status", "enabled") == "enabled" and data.get(
            "is_active",
            True,
        )
        return data

    def _normalize_status(self, value: object) -> str:
        normalized = str(value or "enabled").strip().lower()
        if normalized in {"enabled", "active"}:
            return "enabled"
        if normalized in {"disabled", "inactive"}:
            return "disabled"
        return "enabled"

    def _normalize_language(self, value: object) -> str:
        normalized = str(value or "EN").strip().upper()
        return normalized if normalized in {"EN", "DE", "RU"} else "EN"

    def _infer_tools(self, text: str | None) -> list[str]:
        normalized_text = text or ""
        return list(
            _infer_tools_cached(
                normalized_text,
                "",
                "",
                "",
                "",
            )
        )

    async def generate_short_description(self, payload: AgentDescriptionGenerateRequest) -> str:
        input_text = (
            "Write a useful 3-4 sentence description for an AI agent.\n"
            f"Agent name: {payload.name}\n"
            f"Agent role: {payload.role or 'Not provided'}\n\n"
            "Requirements:\n"
            "- Write 3 to 4 complete sentences.\n"
            "- Explain what the agent does, who it helps, and what kind of outputs it produces.\n"
            "- Mention practical use cases and the value the user should expect.\n"
            "- Use clear product language suitable for showing in the agent creation form.\n"
            "- Do not use bullet points, markdown headings, or placeholder text.\n"
            "- Return only the description text."
        )
        return await self._generate_text(
            input_text,
            fallback=self._fallback_short_description(payload.name, payload.role),
        )

    async def generate_builder_system_prompt(
        self,
        payload: AgentSystemPromptGenerateRequest,
    ) -> str:
        input_text = (
            "Create a detailed production-ready system prompt for an AI agent that the user can review and edit.\n"
            f"Agent name: {payload.name}\n"
            f"Short description: {payload.short_description}\n"
            f"Category tag: {payload.category_tag or 'None'}\n"
            f"Base template: {payload.base_template or 'blank'}\n\n"
            "Requirements:\n"
            "- Write a complete system prompt, not a summary.\n"
            "- Do not force one fixed response template for every answer.\n"
            "- Tell the agent to first understand the user's intent, then choose the best response format dynamically.\n"
            "- Use sections only when they genuinely improve readability for a longer or more complex answer.\n"
            "- Use bullets only when they make multiple points easier to scan.\n"
            "- Keep small questions small and deep questions detailed.\n"
            "- Define the agent's role, goal, scope, and boundaries.\n"
            "- Explain the ideal user, supported tasks, and unsupported tasks.\n"
            "- Tell the agent to answer the user's exact request with specific, non-generic guidance.\n"
            "- Tell the agent to avoid generic capability statements such as 'I can help with...' when the request is already actionable.\n"
            "- Tell the agent to produce the actual deliverable first: draft, answer, plan, comparison, recommendation, checklist, or script.\n"
            "- Tell the agent to write outputs that could be shown directly to a client, buyer, or teammate when appropriate.\n"
            "- Require the agent to choose the best representation for each question type: plain paragraph, short bullets, numbered steps, headings with sections, table, script, code, analysis, comparison, or troubleshooting flow.\n"
            "- Require direct/simple questions to receive a direct answer first without unnecessary headings.\n"
            "- Require technical guidance, architecture, roadmap, or analysis to use structured headings and bullets where useful.\n"
            "- Require rewriting, chatting, email, proposal, or message-writing tasks to feel human, natural, and ready to use, not report-like unless requested.\n"
            "- Require code/debugging answers to briefly explain the issue and then provide code or concrete steps in proper code fences when needed.\n"
            "- Require recommendations to appear early, followed by only the reasoning needed for confidence.\n"
            "- Require practical outputs such as steps, examples, scripts, tables, checklists, or templates when useful.\n"
            "- Require the agent to use details from the user's message instead of placeholders like 'your product'.\n"
            "- Tell the agent to reuse the user's nouns, constraints, audience, and goal so the answer feels specific.\n"
            "- Explain how to handle missing context: state assumptions, give useful guidance, then ask one question if needed.\n"
            "- Require different answers across turns by using the latest message and conversation history.\n"
            "- Include formatting rules for readable Markdown answers.\n"
            "- Include safety and honesty rules: do not invent facts, prices, policies, legal/medical claims, or private data.\n"
            "- Include escalation rules for unsupported, risky, or ambiguous requests.\n"
            "- Include response style, formatting, and quality rules.\n"
            "- Explain how to handle unknown or unsupported requests without inventing facts.\n"
            "- Keep it descriptive, specific to this agent, and directly usable as a system prompt.\n"
            "- Return only the system prompt text."
        )
        return await self._generate_text(
            input_text,
            fallback=self._fallback_system_prompt(
                name=payload.name,
                short_description=payload.short_description,
                category_tag=payload.category_tag,
                base_template=payload.base_template,
            ),
        )

    async def generate_welcome_message(self, payload: AgentWelcomeMessageGenerateRequest) -> str:
        input_text = (
            "Write a polished first welcome message for an AI agent.\n"
            f"Agent name: {payload.name}\n"
            f"Short description: {payload.short_description}\n"
            f"Category tag: {payload.category_tag or 'None'}\n"
            f"Base template: {payload.base_template or 'blank'}\n\n"
            "Requirements:\n"
            "- One or two sentences only.\n"
            "- Sound professional, helpful, and ready for production use.\n"
            "- Invite the user to share what they need.\n"
            "- Return only the welcome message text."
        )
        return await self._generate_text(
            input_text,
            fallback=self._fallback_welcome_message(
                name=payload.name,
                short_description=payload.short_description,
            ),
        )

    async def _generate_system_prompt(self, payload: AgentAICreate) -> str:
        input_text = (
            "Create a detailed production-ready system prompt for an AI agent that the user can review and edit.\n"
            f"Agent name: {payload.name}\n"
            f"Role: {payload.role or 'AI Agent'}\n"
            f"Purpose: {payload.purpose}\n"
            f"Tone: {payload.tone}\n"
            f"Extra instructions: {payload.instructions or 'None'}\n\n"
            "Requirements:\n"
            "- Write a complete system prompt, not a summary.\n"
            "- Do not force one fixed response template for every answer.\n"
            "- Require the agent to first understand the user's intent, then choose the best response format dynamically.\n"
            "- Use sections only when they genuinely improve readability for a longer or more complex answer.\n"
            "- Use bullets only when they make multiple points easier to scan.\n"
            "- Keep small questions small and deep questions detailed.\n"
            "- Define the role, goal, scope, and boundaries.\n"
            "- Explain the ideal user, supported tasks, and unsupported tasks.\n"
            "- Require the agent to answer the user's exact request with specific, actionable guidance.\n"
            "- Require the agent to avoid generic capability statements when the user's request is already actionable.\n"
            "- Require the agent to produce the actual deliverable first: draft, answer, plan, comparison, recommendation, checklist, or script.\n"
            "- Require the agent to write outputs that could be shown directly to a client, buyer, or teammate when appropriate.\n"
            "- Require the agent to choose the best representation for each question type: plain paragraph, short bullets, numbered steps, headings with sections, table, script, code, analysis, comparison, or troubleshooting flow.\n"
            "- Require direct/simple questions to receive a direct answer first without unnecessary headings.\n"
            "- Require technical guidance, architecture, roadmap, or analysis to use structured headings and bullets where useful.\n"
            "- Require rewriting, chatting, email, proposal, or message-writing tasks to feel human, natural, and ready to use, not report-like unless requested.\n"
            "- Require code/debugging answers to briefly explain the issue and then provide code or concrete steps in proper code fences when needed.\n"
            "- Require recommendations to appear early, followed by only the reasoning needed for confidence.\n"
            "- Require concrete examples, scripts, checklists, tables, or next steps when useful.\n"
            "- Require the agent to reuse user-provided details and avoid generic placeholders.\n"
            "- Require the agent to reuse the user's nouns, constraints, audience, and goal so the answer feels specific.\n"
            "- Require the agent to state assumptions when details are missing and ask at most one clarifying question.\n"
            "- Require the agent to produce a different, context-aware answer each turn by using conversation history.\n"
            "- Include formatting rules for readable Markdown answers.\n"
            "- Include escalation rules for unsupported, risky, or ambiguous requests.\n"
            "- Require the agent to avoid inventing facts, prices, policies, or private data.\n"
            "- Return only the system prompt text."
        )
        return await self._generate_text(
            input_text,
            fallback=self._fallback_system_prompt(
                name=payload.name,
                short_description=payload.purpose,
                category_tag=payload.role,
                base_template=payload.template_type,
                tone=payload.tone,
                instructions=payload.instructions,
            ),
        )

    async def _generate_text(self, input_text: str, fallback: str) -> str:
        if not settings.openai_api_key:
            return fallback

        try:
            _get_openai_client(settings.openai_api_key)
        except ImportError:
            logger.exception("OpenAI SDK is unavailable; using fallback generated text.")
            return fallback

        client = _get_openai_client(settings.openai_api_key)
        started_at = perf_counter()
        try:
            response = await client.responses.create(
                model=settings.default_llm_engine,
                input=input_text,
            )
        except Exception:
            self._log_timed_operation(
                "generate_text.openai_error",
                started_at,
                model=settings.default_llm_engine,
            )
            logger.exception("Text generation failed; using fallback generated text.")
            return fallback
        self._log_timed_operation(
            "generate_text.openai",
            started_at,
            model=settings.default_llm_engine,
        )

        output_text = getattr(response, "output_text", None)
        if output_text:
            return output_text.strip()

        return fallback

    def _fallback_short_description(self, name: str, role: str | None = None) -> str:
        cleaned_name = name.strip()
        lower_name = cleaned_name.lower()
        cleaned_role = (role or "").strip()

        if any(term in lower_name for term in ("sales", "lead", "outreach", "revenue")):
            return (
                f"{cleaned_name} helps sales teams turn product questions, buyer messages, and "
                "lead conversations into clear next steps. It can qualify prospects, suggest "
                "positioning, draft outreach, and guide follow-ups based on the user's sales "
                "goal. The agent is useful for teams that need faster responses, stronger offers, "
                "and more consistent sales communication."
            )
        if any(term in lower_name for term in ("support", "help", "service", "customer")):
            return (
                f"{cleaned_name} helps support teams diagnose customer issues and respond with "
                "clear, practical guidance. It can summarize the problem, suggest troubleshooting "
                "steps, draft customer-friendly replies, and identify when a case should be "
                "escalated. The agent is designed to make support conversations faster, more "
                "consistent, and easier for customers to follow."
            )
        if any(term in lower_name for term in ("hr", "people", "recruit", "talent")):
            return (
                f"{cleaned_name} supports people operations by helping with hiring, employee "
                "communication, onboarding, and policy-related workflows. It can draft structured "
                "messages, organize candidate or employee context, and suggest fair next steps. "
                "The agent helps HR teams communicate clearly while keeping decisions consistent "
                "and process-focused."
            )
        if any(term in lower_name for term in ("legal", "contract", "compliance")):
            return (
                f"{cleaned_name} helps organize legal and compliance requests into clear issue "
                "lists, review points, and next steps. It can summarize contract language, flag "
                "missing context, and prepare questions for legal review without pretending to "
                "be a lawyer. The agent is useful for teams that need structured risk awareness "
                "before escalation."
            )
        if any(term in lower_name for term in ("analytics", "data", "report", "insight")):
            return (
                f"{cleaned_name} helps users turn business questions and raw numbers into clear "
                "analysis. It can define metrics, organize data requirements, explain trends, "
                "summarize findings, and recommend the next action. The agent is useful for "
                "reports, dashboards, performance reviews, and decision support."
            )
        if any(term in lower_name for term in ("marketing", "content", "campaign", "brand")):
            return (
                f"{cleaned_name} helps users plan, write, and improve marketing work for real "
                "campaign goals. It can create content angles, captions, offers, audience "
                "positioning, CTAs, and improvement ideas based on the user's channel and product. "
                "The agent is useful for producing practical marketing output instead of vague "
                "campaign advice."
            )
        if cleaned_role:
            return (
                f"{cleaned_name} works as a {cleaned_role} and helps users complete related tasks "
                "with clear guidance and ready-to-use outputs. It can answer questions, organize "
                "information, draft responses, and suggest practical next steps based on the user's "
                "goal. The agent is designed to make day-to-day work faster, more consistent, and "
                "easier to act on."
            )

        return (
            f"{cleaned_name} helps users complete specialized tasks with clear reasoning, useful "
            "structure, and practical next steps. It can turn vague requests into organized "
            "plans, drafts, checklists, summaries, or recommendations depending on the question. "
            "The agent is designed to give answers that are specific to the user's context instead "
            "of generic assistant replies."
        )

    def _fallback_system_prompt(
        self,
        name: str,
        short_description: str,
        category_tag: str | None = None,
        base_template: str | None = None,
        tone: str = "professional",
        instructions: str | None = None,
    ) -> str:
        role = category_tag or base_template or "AI assistant"
        extra_instructions = (
            f"\n- Follow these additional instructions: {instructions.strip()}"
            if instructions and instructions.strip()
            else ""
        )
        return (
            f"You are {name.strip()}, a {role} focused on: {short_description.strip()}\n\n"
            "Role and goal:\n"
            "- Help the user complete the task they asked for, not just learn what the agent does.\n"
            "- Adapt every answer to the user's product, audience, channel, data, constraints, or goal.\n\n"
            "Scope:\n"
            "- Support requests that match the agent purpose and role.\n"
            "- When a request is outside scope, explain the limitation briefly and still provide the safest useful next step.\n"
            "- Do not pretend to have access to private data, live systems, files, tools, or policies unless they are provided in the conversation.\n\n"
            "Answer quality rules:\n"
            f"- Use a {tone} tone.\n"
            "- Do not force one fixed template for every answer.\n"
            "- First understand the user's intent, then choose the best response format dynamically.\n"
            "- Choose between plain paragraph, short bullets, numbered steps, headings with sections, table, script, code, analysis, comparison, or troubleshooting flow based on what best fits the request.\n"
            "- For direct or simple questions, answer directly without unnecessary headings.\n"
            "- For explanations or teaching, use natural paragraphs and add sections only when helpful.\n"
            "- For technical guidance, architecture, roadmap, or analysis, use structured headings and bullets where they improve readability.\n"
            "- For rewriting, chatting, email, proposal, or message-writing tasks, output a human, natural, ready-to-use answer rather than a report unless the user asks for a report.\n"
            "- For code/debugging, explain briefly, then provide code or concrete steps in proper code fences when useful.\n"
            "- Give specific, practical guidance with enough detail to act on immediately.\n"
            "- Keep the output brief but descriptive whenever possible.\n"
            "- For complex or high-value requests, give a fuller ChatGPT-style answer with reasoning, examples, and useful detail.\n"
            "- For simple requests, keep the answer short and direct.\n"
            "- Include examples, scripts, checklists, calculations, tables, or templates when useful.\n"
            "- Do not use generic placeholders if the user provided real details.\n"
            "- If details are missing, state reasonable assumptions and continue with useful guidance.\n"
            "- Ask at most one clarifying question, and place it after the useful answer.\n"
            "- If the request could mean multiple things, answer from the strongest interpretation first and then ask which meaning the user intended.\n"
            "- If the user's meaning is unclear, end with a natural follow-up asking what they want to clarify or continue with next.\n"
            "- For writing tasks, produce the actual draft before explaining it.\n"
            "- For sales or marketing tasks, include offer, audience, channel, CTA, follow-up, and improvement advice when relevant.\n"
            "- For analysis tasks, include metrics, method, evidence, interpretation, and recommendation when relevant.\n"
            "- For technical tasks, give the implementation or commands before explanation when possible.\n"
            "- If you do not know something, say so and suggest the next best step.\n"
            "- Do not invent facts, policies, prices, or private data.\n"
            "- Avoid repeating the same answer across turns; use the latest message and conversation history.\n\n"
            "Formatting rules:\n"
            "- Use normal text by default.\n"
            "- Use clean Markdown only when it improves readability.\n"
            "- Do not always start with headings.\n"
            "- Do not always use bullets.\n"
            "- Use short headings, numbered steps, bullets, or tables only when they fit the user's request.\n"
            "- Use valid Markdown that renders cleanly with remark-gfm.\n"
            "- Use fenced code blocks for code.\n"
            "- Use bold text only when emphasis improves clarity.\n"
            "- Keep the answer easy to scan, but include enough substance to be useful.\n\n"
            "Missing information:\n"
            "- If important details are missing, state your assumptions clearly.\n"
            "- Give the strongest useful answer you can from available context.\n"
            "- Ask at most one focused clarifying question at the end."
            f"{extra_instructions}"
        )

    def _fallback_welcome_message(self, name: str, short_description: str) -> str:
        description = short_description.strip().rstrip(".!?")
        return (
            f"Hi, I'm {name.strip()}. I can help you {description}. "
            "Share what you need, and I'll guide you through the next best steps."
        )

    async def update_agent(
        self,
        agent_id: str,
        payload: AgentUpdate,
        user: UserDocument,
    ) -> AgentResponse:
        existing = await self._get_agent_document(agent_id, user)
        update_data = self._normalize_agent_update(payload.model_dump(exclude_unset=True))
        updated = await self._agents.update_by_id(
            existing.id or "",
            update_data,
        )
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        query_counts = await self._count_queries_30d_by_agent(user.id or "", [updated.id or ""])
        return self._agent_response(updated, queries_30d=query_counts.get(updated.id or "", 0))

    def _normalize_agent_update(self, data: dict) -> dict:
        if not data:
            return data
        if "purpose" in data and "description" not in data:
            data["description"] = data["purpose"]
        if "llm_engine" in data and "model" not in data:
            data["model"] = data["llm_engine"]
        if "model" in data and "llm_engine" not in data:
            data["llm_engine"] = data["model"]
        if "status" in data:
            data["status"] = self._normalize_status(data["status"])
            data["is_active"] = data["status"] == "enabled" and data.get("is_active", True)
        if "language" in data:
            data["language"] = self._normalize_language(data["language"])
        if "knowledge_text" in data and isinstance(data["knowledge_text"], str):
            data["knowledge_text"] = self._normalize_knowledge_text(data["knowledge_text"])
        return data

    def _normalize_knowledge_text(self, text: str) -> str:
        normalized = re.sub(r"\r\n?", "\n", text).strip()
        if len(normalized) <= MAX_AGENT_KNOWLEDGE_CHARS:
            return normalized
        return normalized[:MAX_AGENT_KNOWLEDGE_CHARS].rstrip()

    def extract_knowledge_text(
        self,
        *,
        file_name: str,
        content_type: str | None,
        content: bytes,
    ) -> str:
        started_at = perf_counter()
        suffix = Path(file_name).suffix.lower()
        normalized_content_type = (content_type or "").lower()

        if suffix == ".pdf" or normalized_content_type == "application/pdf":
            from pypdf import PdfReader

            from io import BytesIO

            reader = PdfReader(BytesIO(content))
            extracted_pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(part.strip() for part in extracted_pages if part.strip())
            normalized_text = self._normalize_knowledge_text(text)
            self._log_timed_operation(
                "extract_knowledge_text.pdf",
                started_at,
                file_name=file_name,
                characters=len(normalized_text),
            )
            return normalized_text

        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError:
            decoded = content.decode("latin-1", errors="ignore")

        normalized_text = self._normalize_knowledge_text(decoded)
        self._log_timed_operation(
            "extract_knowledge_text.text",
            started_at,
            file_name=file_name,
            characters=len(normalized_text),
        )
        return normalized_text

    async def extract_knowledge_text_with_ai(
        self,
        *,
        file_name: str,
        content_type: str | None,
        content: bytes,
    ) -> str:
        """Extract and normalize document knowledge with the configured AI model.

        The local parser remains a deterministic fallback when an AI provider is
        unavailable, but PDFs are sent as files so scanned/layout-heavy content
        can be interpreted by the model instead of relying on OCR alone.
        """
        fallback = self.extract_knowledge_text(
            file_name=file_name,
            content_type=content_type,
            content=content,
        )
        if not settings.openai_api_key:
            return fallback

        try:
            client = _get_openai_client(settings.openai_api_key)
            suffix = Path(file_name).suffix.lower()
            is_pdf = suffix == ".pdf" or (content_type or "").lower() == "application/pdf"
            is_image = (content_type or "").lower().startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
            if is_pdf or is_image:
                import base64

                mime_type = content_type or ("image/png" if is_image else "application/pdf")
                data_url = f"data:{mime_type};base64,{base64.b64encode(content).decode('ascii')}"
                input_content = (
                    [{"type": "input_image", "image_url": data_url}]
                    if is_image
                    else [{"type": "input_file", "filename": file_name, "file_data": data_url}]
                )
            else:
                input_content = [
                    {
                        "type": "input_text",
                        "text": f"Extract and normalize this document text:\n\n{fallback}",
                    },
                ]
            response = await client.responses.create(
                model=settings.default_llm_engine,
                instructions=(
                    "Extract factual knowledge for an AI agent. Preserve names, numbers, prices, "
                    "currencies, dates, rules, eligibility, and exceptions exactly. Remove boilerplate, "
                    "do not invent or summarize away important details, and return only clean structured "
                    "plain text suitable for a knowledge base."
                ),
                input=[{"role": "user", "content": input_content}],
            )
            output_text = getattr(response, "output_text", None)
            if output_text and output_text.strip():
                return self._normalize_knowledge_text(output_text)
        except Exception:
            logger.exception("AI knowledge extraction failed; using parser fallback", extra={"file_name": file_name})
        return fallback
    async def delete_agent(self, agent_id: str, user: UserDocument) -> None:
        deleted = await self._agents.delete_owned(agent_id, user.id or "")
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        await self._chats.delete_for_agent(agent_id)
