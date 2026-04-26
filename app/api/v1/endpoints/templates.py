from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_service_factory
from app.factories.service_factory import ServiceFactory
from app.models.user import UserDocument
from app.schemas.template import TemplateResponse

router = APIRouter()


@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    _ = current_user
    return await factory.template_service.list_templates()
