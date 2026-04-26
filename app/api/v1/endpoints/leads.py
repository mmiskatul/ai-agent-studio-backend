from fastapi import APIRouter, Depends, status

from app.dependencies import get_current_user, get_service_factory
from app.factories.service_factory import ServiceFactory
from app.models.user import UserDocument
from app.schemas.common import ApiResponse
from app.schemas.lead import LeadCreate, LeadResponse

router = APIRouter()


@router.get("", response_model=list[LeadResponse])
async def list_leads(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.lead_service.list_leads(current_user)


@router.post("", response_model=ApiResponse[LeadResponse], status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    lead = await factory.lead_service.create_lead(payload, current_user)
    return ApiResponse(
        message="Lead created successfully",
        data=lead,
    )
