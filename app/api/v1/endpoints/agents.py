from fastapi import APIRouter, Depends, Response, status

from app.core.config import settings
from app.dependencies import get_current_user, get_service_factory
from app.factories.service_factory import ServiceFactory
from app.models.user import UserDocument
from app.schemas.agent import (
    AgentAICreate,
    AgentBuilderCreate,
    AgentConfigResponse,
    AgentCreate,
    AgentDescriptionGenerateRequest,
    AgentDescriptionGenerateResponse,
    AgentRegistryRebuildResponse,
    AgentRouteRequest,
    AgentRouteResponse,
    AgentResponse,
    AgentSystemPromptGenerateRequest,
    AgentSystemPromptGenerateResponse,
    AgentUpdate,
    AgentWelcomeMessageGenerateRequest,
    AgentWelcomeMessageGenerateResponse,
    LLMEngineOptionsResponse,
    ToolResponse,
)
from app.schemas.chat import ChatSendResponse, MessageCreate
from app.tools.registry import default_tool_registry

router = APIRouter()


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.agent_service.list_agents(current_user)


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: AgentCreate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.agent_service.create_agent(payload, current_user)


@router.post("/builder", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_builder_agent(
    payload: AgentBuilderCreate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.agent_service.create_builder_agent(payload, current_user)


@router.post("/ai", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_ai_agent(
    payload: AgentAICreate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.agent_service.create_ai_agent(payload, current_user)


@router.get("/llm-engines", response_model=LLMEngineOptionsResponse)
async def list_llm_engines():
    return LLMEngineOptionsResponse(
        default_engine=settings.default_llm_engine,
        engines=settings.llm_engine_options,
    )


@router.get("/configs", response_model=list[AgentConfigResponse])
async def list_agent_configs(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.agent_service.list_agent_configs(current_user)


@router.get("/tools", response_model=list[ToolResponse])
async def list_agent_tools():
    registry = default_tool_registry()
    return [
        ToolResponse(name=tool.name, description=tool.description)
        for tool in registry.require_many(registry.list_names())
    ]


@router.post("/route", response_model=AgentRouteResponse)
async def route_agent(
    payload: AgentRouteRequest,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.agent_service.route_agent(
        current_user,
        task=payload.task,
        agent_key=payload.agent_key,
    )


@router.post("/registry/rebuild", response_model=AgentRegistryRebuildResponse)
async def rebuild_agent_registry(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.agent_service.rebuild_registry(current_user)


@router.post("/seed", response_model=list[AgentResponse], status_code=status.HTTP_201_CREATED)
async def seed_default_agents(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.agent_service.seed_default_agents(current_user)


@router.post("/generate-description", response_model=AgentDescriptionGenerateResponse)
async def generate_agent_description(
    payload: AgentDescriptionGenerateRequest,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    _ = current_user
    short_description = await factory.agent_service.generate_short_description(payload)
    return AgentDescriptionGenerateResponse(short_description=short_description)


@router.post("/generate-system-prompt", response_model=AgentSystemPromptGenerateResponse)
async def generate_agent_system_prompt(
    payload: AgentSystemPromptGenerateRequest,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    _ = current_user
    system_prompt = await factory.agent_service.generate_builder_system_prompt(payload)
    return AgentSystemPromptGenerateResponse(system_prompt=system_prompt)


@router.post("/generate-welcome-message", response_model=AgentWelcomeMessageGenerateResponse)
async def generate_agent_welcome_message(
    payload: AgentWelcomeMessageGenerateRequest,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    _ = current_user
    welcome_message = await factory.agent_service.generate_welcome_message(payload)
    return AgentWelcomeMessageGenerateResponse(welcome_message=welcome_message)


@router.post("/{agent_id}/chat", response_model=ChatSendResponse)
async def chat_with_agent(
    agent_id: str,
    payload: MessageCreate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    user_message, assistant_message = await factory.chat_service.send_message(
        agent_id,
        current_user,
        payload.content,
    )
    return ChatSendResponse(user_message=user_message, assistant_message=assistant_message)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.agent_service.get_agent(agent_id, current_user)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.agent_service.update_agent(agent_id, payload, current_user)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    await factory.agent_service.delete_agent(agent_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
