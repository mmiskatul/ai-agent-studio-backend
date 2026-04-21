from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status

from app.dependencies import get_current_user, get_service_factory
from app.factories.service_factory import ServiceFactory
from app.models.user import UserDocument
from app.schemas.agent import (
    AgentAICreate,
    AgentBuilderCreate,
    AgentCreate,
    AgentKnowledgeCreateResponse,
    AgentResponse,
    AgentUpdate,
)
from app.schemas.knowledge import KnowledgeResponse

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


@router.post(
    "/builder/with-knowledge",
    response_model=AgentKnowledgeCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_builder_agent_with_knowledge(
    name: str = Form(...),
    short_description: str = Form(...),
    base_template: str = Form(default="blank"),
    category_tag: str | None = Form(default=None),
    system_prompt: str = Form(...),
    welcome_message: str | None = Form(default=None),
    llm_engine: str = Form(default="gpt-4o"),
    temperature: float = Form(default=0.7),
    status_value: str = Form(default="active", alias="status"),
    upload_data_source: UploadFile | None = File(default=None),
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    agent = await factory.agent_service.create_builder_agent(
        AgentBuilderCreate(
            name=name,
            short_description=short_description,
            base_template=base_template,
            category_tag=category_tag,
            system_prompt=system_prompt,
            welcome_message=welcome_message,
            llm_engine=llm_engine,
            temperature=temperature,
            status=status_value,
        ),
        current_user,
    )
    knowledge = None
    if upload_data_source is not None:
        knowledge = await factory.knowledge_service.upload_knowledge(
            agent.id or "",
            current_user,
            upload_data_source,
        )
    return AgentKnowledgeCreateResponse(agent=agent, knowledge=knowledge)


@router.post("/ai", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_ai_agent(
    payload: AgentAICreate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.agent_service.create_ai_agent(payload, current_user)


@router.post(
    "/ai/with-knowledge",
    response_model=AgentKnowledgeCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ai_agent_with_knowledge(
    name: str = Form(...),
    purpose: str = Form(...),
    role: str | None = Form(default=None),
    template_type: str | None = Form(default=None),
    status_value: str = Form(default="active", alias="status"),
    instructions: str | None = Form(default=None),
    tone: str = Form(default="professional"),
    file: UploadFile | None = File(default=None),
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    agent = await factory.agent_service.create_ai_agent(
        AgentAICreate(
            name=name,
            purpose=purpose,
            role=role,
            template_type=template_type,
            status=status_value,
            instructions=instructions,
            tone=tone,
        ),
        current_user,
    )
    knowledge = None
    if file is not None:
        knowledge = await factory.knowledge_service.upload_knowledge(
            agent.id or "",
            current_user,
            file,
        )
    return AgentKnowledgeCreateResponse(agent=agent, knowledge=knowledge)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.agent_service.get_agent(agent_id, current_user)


@router.get("/{agent_id}/knowledge", response_model=list[KnowledgeResponse])
async def list_agent_knowledge(
    agent_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.knowledge_service.list_knowledge(agent_id, current_user)


@router.post(
    "/{agent_id}/knowledge",
    response_model=KnowledgeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_agent_knowledge(
    agent_id: str,
    file: UploadFile = File(...),
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.knowledge_service.upload_knowledge(agent_id, current_user, file)


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
