from fastapi import HTTPException, status

from app.models.staff import StaffDocument
from app.models.user import UserDocument
from app.repositories.agent_repository import AgentRepository
from app.repositories.staff_repository import StaffRepository
from app.schemas.staff import StaffCreate, StaffResponse, StaffUpdate


class StaffService:
    def __init__(self, staff: StaffRepository, agents: AgentRepository) -> None:
        self._staff = staff
        self._agents = agents

    async def list_staff(self, user: UserDocument) -> list[StaffResponse]:
        members = await self._staff.list_by_user(user.id or "")
        return [self._to_response(member) for member in members]

    async def create_staff(self, payload: StaffCreate, user: UserDocument) -> StaffResponse:
        await self._validate_agent_access(payload.assigned_agent_ids, user)
        created = await self._staff.create(
            StaffDocument(
                user_id=user.id or "",
                name=payload.name,
                email=payload.email,
                role=payload.role,
                assigned_agent_ids=payload.assigned_agent_ids,
            )
        )
        return self._to_response(created)

    async def update_staff(self, staff_id: str, payload: StaffUpdate, user: UserDocument) -> StaffResponse:
        existing = await self._staff.get_owned(staff_id, user.id or "")
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")
        assigned_agent_ids = payload.assigned_agent_ids if payload.assigned_agent_ids is not None else existing.assigned_agent_ids
        await self._validate_agent_access(assigned_agent_ids, user)
        updated = await self._staff.update_by_id(
            staff_id,
            {
                key: value
                for key, value in payload.model_dump(exclude_unset=True).items()
            },
        )
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")
        return self._to_response(updated)

    async def delete_staff(self, staff_id: str, user: UserDocument) -> None:
        deleted = await self._staff.delete_owned(staff_id, user.id or "")
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")

    async def _validate_agent_access(self, agent_ids: list[str], user: UserDocument) -> None:
        for agent_id in agent_ids:
            agent = await self._agents.get_owned(agent_id, user.id or "")
            if agent is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned agent not found")

    def _to_response(self, member: StaffDocument) -> StaffResponse:
        return StaffResponse.model_validate({**member.model_dump(), "id": member.id or ""})
