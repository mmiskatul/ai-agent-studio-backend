from fastapi import APIRouter

from app.api.v1.endpoints import agents, auth, dashboard, health, overview

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(overview.router, prefix="/overview", tags=["overview"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
