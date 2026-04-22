import json
from datetime import timedelta
from logging import getLogger

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
                status="active" if config.is_active else "inactive",
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
    ) -> tuple[AgentDocument, ChatDocument, str, ChatMemoryDocument]:
        agent = await self._get_agent_document(agent_id, user)
        config = self._agent_config(agent)
        if not config.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This agent is inactive and cannot generate responses.",
            )

        chat = await self._get_or_create_memory_chat(agent, user, content, chat_id=chat_id)
        user_message = await self._chats.add_message(
            MessageDocument(chat_id=chat.id or "", sender_type="user", content=content),
        )
        messages = await self._chats.list_messages(chat.id or "")
        response = await self._generate_memory_response(
            agent=agent,
            config=config,
            chat=chat,
            current_message=user_message,
            messages=messages,
        )
        parsed_response = parse_agent_json_response(response)
        assistant_message = await self._chats.add_message(
            MessageDocument(
                chat_id=chat.id or "",
                sender_type="assistant",
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
    ) -> tuple[AgentDocument, ChatDocument | None, list[MessageDocument]]:
        agent = await self._get_agent_document(agent_id, user)
        chat = (
            await self._chats.get_owned_chat(user.id or "", agent.id or "", chat_id)
            if chat_id
            else await self._chats.get_for_agent(user.id or "", agent.id or "")
        )
        if chat is None:
            return agent, None, []
        messages = await self._chats.list_messages(chat.id or "")
        return agent, chat, messages

    async def list_agent_response_pages(
        self,
        agent_id: str,
        user: UserDocument,
    ) -> list[tuple[ChatDocument, int]]:
        agent = await self._get_agent_document(agent_id, user)
        chats = await self._chats.list_by_agent(user.id or "", agent.id or "")
        message_counts = await self._chats.count_messages_by_chat_ids(
            [chat.id or "" for chat in chats if chat.id],
        )
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
                detail="This agent is inactive and cannot create response pages.",
            )
        return await self._chats.create(
            ChatDocument(
                user_id=user.id or "",
                agent_id=agent.id or "",
                title=title.strip() if title and title.strip() else "New page",
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
        messages = await self._chats.list_messages(chat.id or "")
        return agent, chat, messages

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
                detail="This agent is inactive and cannot generate responses.",
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

        next_assistant = await self._chats.get_next_assistant_message(
            chat.id or "",
            message.created_at,
        )
        messages = await self._chats.list_messages(chat.id or "")
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
            await self._chats.add_message(
                MessageDocument(
                    chat_id=chat.id or "",
                    sender_type="assistant",
                    content=parsed_response.response,
                ),
            )
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

        messages = await self._chats.list_messages(chat.id or "")
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
                detail="This agent is inactive and cannot generate responses.",
            )

        chat, message = await self._get_owned_response_message(agent, user, message_id)
        paired_assistant = None
        if message.sender_type == "user":
            paired_assistant = await self._chats.get_next_assistant_message(
                chat.id or "",
                message.created_at,
            )

        deleted = await self._chats.delete_message(message.id or "")
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        if paired_assistant is not None:
            await self._chats.delete_message(paired_assistant.id or "")

        messages = await self._chats.list_messages(chat.id or "")
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
        message = await self._chats.get_message(message_id)
        if message is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
        chat = await self._chats.get_owned_chat(user.id or "", agent.id or "", message.chat_id)
        if chat is None:
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

    def _build_title(self, content: str) -> str:
        title = " ".join(content.strip().split())
        if len(title) <= 80:
            return title
        return f"{title[:77].rstrip()}..."

    def _build_memory_title(
        self,
        *,
        previous_memory: ChatMemoryDocument,
        system_summary: str,
        messages: list[MessageDocument],
    ) -> str:
        latest_user_message = next(
            (
                " ".join(message.content.strip().split())
                for message in reversed(messages)
                if message.sender_type == "user" and message.content.strip()
            ),
            "",
        )
        if latest_user_message:
            return self._build_title(latest_user_message)
        if system_summary.strip():
            return self._build_title(system_summary.strip())
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
    ) -> str:
        memory = self._parse_chat_memory(chat.memory, chat.summary)
        prompt = self._response_prompt_builder.build(
            agent=agent,
            config=config,
            memory=memory,
            current_message=current_message.content,
            messages=messages,
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
                AsyncOpenAI,
                RateLimitError,
            )
        except ImportError:
            return self._fallback_agent_response(
                config,
                current_message.content,
                self._memory_context_text(memory),
            )

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        try:
            response = await client.responses.create(
                model=config.model or settings.default_llm_engine,
                instructions=self._response_prompt_builder.json_instructions,
                input=prompt,
                temperature=config.temperature,
            )
        except (APIConnectionError, APIError, APIStatusError, RateLimitError):
            return self._fallback_agent_response(
                config,
                current_message.content,
                self._memory_context_text(memory),
            )

        output_text = getattr(response, "output_text", None)
        if output_text and output_text.strip():
            return output_text.strip()
        return self._fallback_agent_response(
            config,
            current_message.content,
            self._memory_context_text(memory),
        )

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
        agent = AgentDocument(
            user_id=user.id or "",
            name=payload.name,
            role=payload.category_tag or payload.base_template or "AgentLab",
            purpose=payload.short_description,
            description=payload.short_description,
            template_type=payload.base_template,
            category_tag=payload.category_tag,
            system_prompt=payload.system_prompt,
            welcome_message=payload.welcome_message,
            llm_engine=payload.llm_engine,
            model=payload.llm_engine,
            temperature=payload.temperature,
            status=payload.status,
            tools=self._infer_tools(payload.category_tag or payload.base_template),
            is_active=payload.status == "active",
        )
        return self._agent_response(await self._agents.create(agent))

    async def create_ai_agent(self, payload: AgentAICreate, user: UserDocument) -> AgentResponse:
        system_prompt = await self._generate_system_prompt(payload)
        agent = AgentDocument(
            user_id=user.id or "",
            name=payload.name,
            role=payload.role or "AI Agent",
            purpose=payload.purpose,
            description=payload.purpose,
            template_type=payload.template_type,
            category_tag=payload.template_type,
            system_prompt=system_prompt,
            llm_engine=settings.default_llm_engine,
            model=settings.default_llm_engine,
            status=payload.status,
            tools=self._infer_tools(payload.role or payload.template_type),
            is_active=payload.status == "active",
        )
        return self._agent_response(await self._agents.create(agent))

    async def _count_queries_30d_by_agent(
        self,
        user_id: str,
        agent_ids: list[str] | None = None,
    ) -> dict[str, int]:
        chats = await self._chats.list_by_user(user_id)
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
        return AgentResponse.model_validate(
            {
                **agent.model_dump(),
                "id": agent.id or "",
                "description": agent.description or agent.purpose,
                "model": agent.model or agent.llm_engine,
                "is_active": agent.is_active and agent.status == "active",
                "queries_30d": queries_30d,
            },
        )

    def _agent_config(self, agent: AgentDocument) -> AgentConfig:
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
            is_active=agent.is_active and agent.status == "active",
        )

    def _normalize_agent_config(self, data: dict) -> dict:
        data["description"] = data.get("description") or data.get("purpose") or data.get("role")
        data["model"] = data.get("model") or data.get("llm_engine") or settings.default_llm_engine
        data["llm_engine"] = data.get("llm_engine") or data["model"]
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
        data["is_active"] = data.get("status", "active") == "active" and data.get(
            "is_active",
            True,
        )
        return data

    def _infer_tools(self, text: str | None) -> list[str]:
        lowered_text = (text or "").lower()
        tools = ["summarizer"]
        if any(term in lowered_text for term in ("sales", "lead", "revenue", "marketing")):
            tools.append("sales_playbook")
        if any(term in lowered_text for term in ("data", "analytics", "report", "metric")):
            tools.append("calculator")
        if any(term in lowered_text for term in ("search", "research", "web")):
            tools.append("search")
        return tools

    async def generate_short_description(self, payload: AgentDescriptionGenerateRequest) -> str:
        input_text = (
            "Write a useful 3-4 sentence description for an AI agent.\n"
            f"Agent name: {payload.name}\n\n"
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
            fallback=self._fallback_short_description(payload.name),
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
            "- Use 6 to 10 clear sections or paragraphs with practical instructions.\n"
            "- Define the agent's role, goal, scope, and boundaries.\n"
            "- Explain the ideal user, supported tasks, and unsupported tasks.\n"
            "- Tell the agent to answer the user's exact request with specific, non-generic guidance.\n"
            "- Tell the agent to avoid generic capability statements such as 'I can help with...' when the request is already actionable.\n"
            "- Tell the agent to produce the actual deliverable first: draft, answer, plan, comparison, recommendation, checklist, or script.\n"
            "- Tell the agent to write outputs that could be shown directly to a client, buyer, or teammate when appropriate.\n"
            "- Require the agent to choose the best representation for each question type: direct answer, plan, checklist, table, script, code, analysis, comparison, or troubleshooting flow.\n"
            "- Require the agent to start with the conclusion or best recommendation before details.\n"
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
            "- Use 6 to 10 clear sections or paragraphs with practical instructions.\n"
            "- Define the role, goal, scope, and boundaries.\n"
            "- Explain the ideal user, supported tasks, and unsupported tasks.\n"
            "- Require the agent to answer the user's exact request with specific, actionable guidance.\n"
            "- Require the agent to avoid generic capability statements when the user's request is already actionable.\n"
            "- Require the agent to produce the actual deliverable first: draft, answer, plan, comparison, recommendation, checklist, or script.\n"
            "- Require the agent to write outputs that could be shown directly to a client, buyer, or teammate when appropriate.\n"
            "- Require the agent to choose the best representation for each question type: direct answer, plan, checklist, table, script, code, analysis, comparison, or troubleshooting flow.\n"
            "- Require the agent to start with the conclusion or best recommendation before details.\n"
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
            from openai import AsyncOpenAI
            from openai import APIError, APIStatusError, RateLimitError
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OpenAI SDK is not installed. Run pip install -r requirements.txt.",
            ) from exc

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        try:
            response = await client.responses.create(
                model=settings.default_llm_engine,
                input=input_text,
            )
        except (RateLimitError, APIStatusError, APIError):
            return fallback

        output_text = getattr(response, "output_text", None)
        if output_text:
            return output_text.strip()

        return fallback

    def _fallback_short_description(self, name: str) -> str:
        cleaned_name = name.strip()
        lower_name = cleaned_name.lower()

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
            "- Start with the direct answer or recommendation.\n"
            "- Choose the best representation for the request: direct answer, numbered plan, checklist, table, script, code, analysis, comparison, or troubleshooting flow.\n"
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
            "- Use short headings, numbered steps, bullets, or tables based on the user's request.\n"
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
            data["is_active"] = data["status"] == "active" and data.get("is_active", True)
        return data

    async def delete_agent(self, agent_id: str, user: UserDocument) -> None:
        deleted = await self._agents.delete_owned(agent_id, user.id or "")
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        await self._chats.delete_for_agent(agent_id)
