from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_service_factory
from app.factories.service_factory import ServiceFactory
from app.models.user import UserDocument
from app.schemas.overview import (
    OverviewActivityItem,
    OverviewAgentSummary,
    OverviewCategorySummary,
    OverviewResponse,
    OverviewStats,
)

router = APIRouter()


@router.get("", response_model=OverviewResponse)
async def get_overview(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.overview_service.get_overview(current_user)


@router.get("/stats", response_model=OverviewStats)
async def get_overview_stats(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    overview = await factory.overview_service.get_overview(current_user)
    return overview.stats


@router.get("/top-agents", response_model=list[OverviewAgentSummary])
async def get_overview_top_agents(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    overview = await factory.overview_service.get_overview(current_user)
    return overview.top_agents


@router.get("/categories", response_model=list[OverviewCategorySummary])
async def get_overview_categories(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    overview = await factory.overview_service.get_overview(current_user)
    return overview.categories


@router.get("/recent-activity", response_model=list[OverviewActivityItem])
async def get_overview_recent_activity(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    overview = await factory.overview_service.get_overview(current_user)
    return overview.recent_activity
