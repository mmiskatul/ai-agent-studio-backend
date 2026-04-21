from fastapi import HTTPException, status

from app.core.config import settings
from app.models.agent import AgentDocument
from app.models.user import UserDocument
from app.repositories.agent_repository import AgentRepository
from app.schemas.agent import AgentAICreate, AgentBuilderCreate, AgentCreate, AgentUpdate


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
            llm_engine=settings.openai_agent_model,
            status=payload.status,
        )
        return await self._agents.create(agent)

    async def _generate_system_prompt(self, payload: AgentAICreate) -> str:
        if not settings.openai_api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OPENAI_API_KEY is not configured",
            )

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OpenAI SDK is not installed. Run pip install -r requirements.txt.",
            ) from exc

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        input_text = (
            "Create a concise, production-ready system prompt for an AI agent.\n"
            f"Agent name: {payload.name}\n"
            f"Role: {payload.role or 'AI Agent'}\n"
            f"Purpose: {payload.purpose}\n"
            f"Tone: {payload.tone}\n"
            f"Extra instructions: {payload.instructions or 'None'}\n\n"
            "Return only the system prompt text."
        )

        response = await client.responses.create(
            model=settings.openai_agent_model,
            input=input_text,
        )
        output_text = getattr(response, "output_text", None)
        if output_text:
            return output_text.strip()

        return (
            f"You are {payload.name}, an AI agent focused on {payload.purpose}. "
            f"Use a {payload.tone} tone and follow the user's instructions carefully."
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
