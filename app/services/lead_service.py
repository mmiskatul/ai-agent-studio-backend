from fastapi import HTTPException, status

from app.models.lead import LeadDocument
from app.models.user import UserDocument
from app.repositories.agent_repository import AgentRepository
from app.repositories.lead_repository import LeadRepository
from app.schemas.lead import LeadCreate, LeadResponse


class LeadService:
    def __init__(self, leads: LeadRepository, agents: AgentRepository) -> None:
        self._leads = leads
        self._agents = agents

    async def list_leads(self, user: UserDocument) -> list[LeadResponse]:
        return [self._to_response(lead) for lead in await self._leads.list_by_user(user.id or "")]

    async def create_lead(self, payload: LeadCreate, user: UserDocument) -> LeadResponse:
        agent = await self._agents.get_owned(payload.agent_id, user.id or "")
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        created = await self._leads.create(
            LeadDocument(
                user_id=user.id or "",
                agent_id=payload.agent_id,
                name=payload.name,
                phone=payload.phone,
                message=payload.message,
            )
        )
        return self._to_response(created)

    def _to_response(self, lead: LeadDocument) -> LeadResponse:
        return LeadResponse.model_validate({**lead.model_dump(), "id": lead.id or ""})
