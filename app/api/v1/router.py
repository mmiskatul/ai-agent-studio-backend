from fastapi import APIRouter

from app.api.v1.endpoints import agents, auth, chats, health, overview

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(overview.router, prefix="/overview", tags=["overview"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(chats.router, prefix="/agents", tags=["chats"])
