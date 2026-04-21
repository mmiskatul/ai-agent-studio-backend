from datetime import timedelta

from fastapi import HTTPException, status

from app.agents.config import AgentConfig
from app.agents.configs import DEFAULT_AGENT_CONFIGS
from app.agents.factory import create_agent
from app.agents.routing import AgentRouter
from app.agents.state import runtime_agent_registry
from app.core.config import settings
from app.models.agent import AgentDocument
from app.models.base import now_utc
from app.models.user import UserDocument
from app.repositories.agent_repository import AgentRepository
from app.repositories.chat_repository import ChatRepository
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
)
from app.tools.registry import default_tool_registry


class AgentService:
    def __init__(self, agents: AgentRepository, chats: ChatRepository) -> None:
        self._agents = agents
        self._chats = chats

    async def list_agents(self, user: UserDocument) -> list[AgentResponse]:
        user_id = user.id or ""
        agents = await self._agents.list_by_user(user_id)
        query_counts = await self._count_queries_30d_by_agent(user_id)
        return [
            self._agent_response(agent, queries_30d=query_counts.get(agent.id or "", 0))
            for agent in agents
        ]

    async def get_agent(self, agent_id: str, user: UserDocument) -> AgentResponse:
        agent = await self._get_agent_document(agent_id, user)
        query_counts = await self._count_queries_30d_by_agent(user.id or "", [agent.id or ""])
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

    async def _get_agent_document(self, agent_id: str, user: UserDocument) -> AgentDocument:
        agent = await self._agents.get_owned(agent_id, user.id or "")
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        return agent

    async def create_agent(self, payload: AgentCreate, user: UserDocument) -> AgentResponse:
        data = self._normalize_agent_config(payload.model_dump())
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
        return query_counts_by_agent

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
            "- Require the agent to choose the best representation for each question type: direct answer, plan, checklist, table, script, code, analysis, comparison, or troubleshooting flow.\n"
            "- Require the agent to start with the conclusion or best recommendation before details.\n"
            "- Require practical outputs such as steps, examples, scripts, tables, checklists, or templates when useful.\n"
            "- Require the agent to use details from the user's message instead of placeholders like 'your product'.\n"
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
            "- Require the agent to choose the best representation for each question type: direct answer, plan, checklist, table, script, code, analysis, comparison, or troubleshooting flow.\n"
            "- Require the agent to start with the conclusion or best recommendation before details.\n"
            "- Require concrete examples, scripts, checklists, tables, or next steps when useful.\n"
            "- Require the agent to reuse user-provided details and avoid generic placeholders.\n"
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
            "- Include examples, scripts, checklists, calculations, tables, or templates when useful.\n"
            "- Do not use generic placeholders if the user provided real details.\n"
            "- If details are missing, state reasonable assumptions and continue with useful guidance.\n"
            "- Ask at most one clarifying question, and place it after the useful answer.\n"
            "- For writing tasks, produce the actual draft before explaining it.\n"
            "- For sales or marketing tasks, include offer, audience, channel, CTA, follow-up, and improvement advice when relevant.\n"
            "- For analysis tasks, include metrics, method, evidence, interpretation, and recommendation when relevant.\n"
            "- For technical tasks, give the implementation or commands before explanation when possible.\n"
            "- If you do not know something, say so and suggest the next best step.\n"
            "- Do not invent facts, policies, prices, or private data.\n"
            "- Avoid repeating the same answer across turns; use the latest message and conversation history.\n\n"
            "Formatting rules:\n"
            "- Use clean Markdown when it improves readability.\n"
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
