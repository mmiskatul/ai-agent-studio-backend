from fastapi import HTTPException, status

from app.core.config import settings
from app.models.agent import AgentDocument
from app.models.user import UserDocument
from app.repositories.agent_repository import AgentRepository
from app.schemas.agent import (
    AgentAICreate,
    AgentBuilderCreate,
    AgentCreate,
    AgentDescriptionGenerateRequest,
    AgentSystemPromptGenerateRequest,
    AgentUpdate,
    AgentWelcomeMessageGenerateRequest,
)


class AgentService:
    def __init__(self, agents: AgentRepository) -> None:
        self._agents = agents

    async def list_agents(self, user: UserDocument) -> list[AgentDocument]:
        return await self._agents.list_by_user(user.id or "")

    async def get_agent(self, agent_id: str, user: UserDocument) -> AgentDocument:
        agent = await self._agents.get_owned(agent_id, user.id or "")
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        return agent

    async def create_agent(self, payload: AgentCreate, user: UserDocument) -> AgentDocument:
        agent = AgentDocument(user_id=user.id or "", **payload.model_dump())
        return await self._agents.create(agent)

    async def create_builder_agent(
        self,
        payload: AgentBuilderCreate,
        user: UserDocument,
    ) -> AgentDocument:
        agent = AgentDocument(
            user_id=user.id or "",
            name=payload.name,
            role=payload.category_tag or payload.base_template or "AgentLab",
            purpose=payload.short_description,
            template_type=payload.base_template,
            category_tag=payload.category_tag,
            system_prompt=payload.system_prompt,
            welcome_message=payload.welcome_message,
            llm_engine=payload.llm_engine,
            temperature=payload.temperature,
            status=payload.status,
        )
        return await self._agents.create(agent)

    async def create_ai_agent(self, payload: AgentAICreate, user: UserDocument) -> AgentDocument:
        system_prompt = await self._generate_system_prompt(payload)
        agent = AgentDocument(
            user_id=user.id or "",
            name=payload.name,
            role=payload.role or "AI Agent",
            purpose=payload.purpose,
            template_type=payload.template_type,
            category_tag=payload.template_type,
            system_prompt=system_prompt,
            llm_engine=settings.default_llm_engine,
            status=payload.status,
        )
        return await self._agents.create(agent)

    async def generate_short_description(self, payload: AgentDescriptionGenerateRequest) -> str:
        input_text = (
            "Write one concise short description for an AI agent.\n"
            f"Agent name: {payload.name}\n\n"
            "Requirements:\n"
            "- One sentence only.\n"
            "- Maximum 120 characters.\n"
            "- Explain what the agent does in practical product language.\n"
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
            "Create a production-ready system prompt for an AI agent.\n"
            f"Agent name: {payload.name}\n"
            f"Short description: {payload.short_description}\n"
            f"Category tag: {payload.category_tag or 'None'}\n"
            f"Base template: {payload.base_template or 'blank'}\n\n"
            "Requirements:\n"
            "- Define the agent's role and boundaries.\n"
            "- Include response style and behavior rules.\n"
            "- Explain how to handle unknown or unsupported requests.\n"
            "- Keep it clear and directly usable as a system prompt.\n"
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
            "Create a concise, production-ready system prompt for an AI agent.\n"
            f"Agent name: {payload.name}\n"
            f"Role: {payload.role or 'AI Agent'}\n"
            f"Purpose: {payload.purpose}\n"
            f"Tone: {payload.tone}\n"
            f"Extra instructions: {payload.instructions or 'None'}\n\n"
            "Return only the system prompt text."
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
                f"{cleaned_name} supports revenue teams by qualifying leads, answering product "
                "questions, and guiding next steps."
            )
        if any(term in lower_name for term in ("support", "help", "service", "customer")):
            return (
                f"{cleaned_name} helps customers resolve issues quickly with accurate, clear, "
                "and consistent support responses."
            )
        if any(term in lower_name for term in ("hr", "people", "recruit", "talent")):
            return (
                f"{cleaned_name} streamlines people operations with structured guidance, "
                "candidate support, and policy-aware responses."
            )
        if any(term in lower_name for term in ("legal", "contract", "compliance")):
            return (
                f"{cleaned_name} assists with legal and compliance workflows by organizing "
                "requests, reviewing context, and surfacing key risks."
            )
        if any(term in lower_name for term in ("analytics", "data", "report", "insight")):
            return (
                f"{cleaned_name} turns business data into clear insights, summaries, and "
                "actionable recommendations."
            )
        if any(term in lower_name for term in ("marketing", "content", "campaign", "brand")):
            return (
                f"{cleaned_name} helps plan, create, and optimize marketing work with clear "
                "brand-aligned recommendations."
            )

        return (
            f"{cleaned_name} helps teams handle specialized workflows with accurate guidance, "
            "clear communication, and reliable task support."
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
            "Behavior rules:\n"
            f"- Use a {tone} tone.\n"
            "- Give clear, practical, and concise answers.\n"
            "- Ask a clarifying question when the user's request is ambiguous.\n"
            "- If you do not know something, say so and suggest the next best step.\n"
            "- Do not invent facts, policies, prices, or private data."
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
    ) -> AgentDocument:
        existing = await self.get_agent(agent_id, user)
        updated = await self._agents.update_by_id(existing.id or "", payload.model_dump(exclude_unset=True))
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        return updated

    async def delete_agent(self, agent_id: str, user: UserDocument) -> None:
        deleted = await self._agents.delete_owned(agent_id, user.id or "")
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
