from fastapi import HTTPException, status

from app.models.agent import AgentDocument
from app.models.user import UserDocument
from app.repositories.agent_repository import AgentRepository
from app.schemas.agent import AgentCreate, AgentUpdate


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
