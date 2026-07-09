from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile, status

from app.core.config import settings
from app.dependencies import get_current_user, get_service_factory
from app.factories.service_factory import ServiceFactory
from app.models.base import now_utc
from app.models.knowledge_extraction_job import KnowledgeExtractionJobDocument
from app.models.user import UserDocument
from app.schemas.agent import (
    AgentAICreate,
    AgentBuilderCreate,
    AgentConfigResponse,
    AgentCreate,
    AgentDescriptionGenerateRequest,
    AgentDescriptionGenerateResponse,
    AgentKnowledgeExtractionJobResponse,
    AgentKnowledgeUploadResponse,
    AgentRegistryRebuildResponse,
    AgentResponsePage,
    AgentResponsePageCreateRequest,
    AgentResponseHistoryResponse,
    AgentResponseGenerateRequest,
    AgentResponseGenerateResponse,
    AgentResponseMessage,
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
from app.schemas.chat import ChatResponse, ChatSendResponse, MessageCreate, MessageResponse, MessageUpdate
from app.schemas.common import ApiResponse
from app.tools.registry import default_tool_registry

router = APIRouter()

ALLOWED_KNOWLEDGE_EXTENSIONS = {".pdf", ".txt", ".md", ".csv", ".json"}


def _knowledge_job_response(job: KnowledgeExtractionJobDocument) -> AgentKnowledgeExtractionJobResponse:
    return AgentKnowledgeExtractionJobResponse(
        job_id=job.id or "",
        status=job.status,
        file_name=job.file_name,
        content_type=job.content_type,
        character_count=job.character_count,
        extracted_text=job.extracted_text,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.agent_service.list_agents(current_user)


@router.post("", response_model=ApiResponse[AgentResponse], status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: AgentCreate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    agent = await factory.agent_service.create_agent(payload, current_user)
    return ApiResponse(
        message="Agent created successfully",
        data=agent,
    )


@router.post("/builder", response_model=ApiResponse[AgentResponse], status_code=status.HTTP_201_CREATED)
async def create_builder_agent(
    payload: AgentBuilderCreate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    agent = await factory.agent_service.create_builder_agent(payload, current_user)
    return ApiResponse(
        message="Agent created successfully",
        data=agent,
    )


@router.post("/ai", response_model=ApiResponse[AgentResponse], status_code=status.HTTP_201_CREATED)
async def create_ai_agent(
    payload: AgentAICreate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    agent = await factory.agent_service.create_ai_agent(payload, current_user)
    return ApiResponse(
        message="Agent created successfully",
        data=agent,
    )


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


@router.post("/knowledge/extract", response_model=AgentKnowledgeUploadResponse)
async def extract_agent_knowledge(
    file: UploadFile = File(...),
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    _ = current_user
    suffix = ""
    if file.filename and "." in file.filename:
        suffix = "." + file.filename.rsplit(".", 1)[-1].lower()
    if suffix not in ALLOWED_KNOWLEDGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Use PDF, TXT, MD, CSV, or JSON.",
        )

    content = await file.read()
    extracted_text = factory.agent_service.extract_knowledge_text(
        file_name=file.filename or "upload.txt",
        content_type=file.content_type,
        content=content,
    )
    if not extracted_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract any readable text from the uploaded file.",
        )

    return AgentKnowledgeUploadResponse(
        file_name=file.filename or "upload.txt",
        content_type=file.content_type or "application/octet-stream",
        extracted_text=extracted_text,
        character_count=len(extracted_text),
    )


async def _process_knowledge_extraction_job(
    *,
    job_id: str,
    file_name: str,
    content_type: str | None,
    content: bytes,
    factory: ServiceFactory,
):
    await factory.knowledge_extraction_jobs.update_status(job_id, status="running")
    try:
        extracted_text = factory.agent_service.extract_knowledge_text(
            file_name=file_name,
            content_type=content_type,
            content=content,
        )
        if not extracted_text:
            raise ValueError("Could not extract any readable text from the uploaded file.")
        await factory.knowledge_extraction_jobs.update_status(
            job_id,
            status="completed",
            extracted_text=extracted_text,
            character_count=len(extracted_text),
        )
    except Exception as exc:
        await factory.knowledge_extraction_jobs.update_status(
            job_id,
            status="failed",
            error=str(exc).strip() or "Extraction failed.",
        )


@router.post("/knowledge/extract-jobs", response_model=AgentKnowledgeExtractionJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_agent_knowledge_extraction_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    suffix = ""
    if file.filename and "." in file.filename:
        suffix = "." + file.filename.rsplit(".", 1)[-1].lower()
    if suffix not in ALLOWED_KNOWLEDGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Use PDF, TXT, MD, CSV, or JSON.",
        )

    content = await file.read()
    job = await factory.knowledge_extraction_jobs.create(
        KnowledgeExtractionJobDocument(
            user_id=current_user.id or "",
            status="pending",
            file_name=file.filename or "upload.txt",
            content_type=file.content_type or "application/octet-stream",
        )
    )
    background_tasks.add_task(
        _process_knowledge_extraction_job,
        job_id=job.id or "",
        file_name=job.file_name,
        content_type=job.content_type,
        content=content,
        factory=factory,
    )
    return _knowledge_job_response(job)


@router.get("/knowledge/extract-jobs/{job_id}", response_model=AgentKnowledgeExtractionJobResponse)
async def get_agent_knowledge_extraction_job(
    job_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    job = await factory.knowledge_extraction_jobs.get_owned(job_id, current_user.id or "")
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge extraction job not found.")
    return _knowledge_job_response(job)


@router.get("/response/pages", response_model=list[AgentResponsePage])
async def list_all_agent_response_pages(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    pages = await factory.agent_service.list_all_agent_response_pages(current_user)
    response_pages: list[AgentResponsePage] = []
    for chat, message_count in pages:
        response_pages.append(
            AgentResponsePage(
                id=chat.id or "",
                agent_id=chat.agent_id or "",
                agent_name=chat.agent_name or "Agent",
                title=chat.title,
                memory_summary=factory.agent_service.parse_memory_summary(chat.memory or chat.summary),
                message_count=message_count,
                created_at=chat.created_at or now_utc(),
                updated_at=chat.updated_at or chat.created_at or now_utc(),
            )
        )
    return response_pages


@router.post("/{agent_id}/response", response_model=AgentResponseGenerateResponse)
async def generate_agent_response(
    agent_id: str,
    payload: AgentResponseGenerateRequest,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    agent, chat, content, memory_summary = await factory.agent_service.generate_agent_response(
        agent_id,
        current_user,
        payload.content,
        chat_id=payload.chat_id,
        attachment_text=payload.attachment_text,
        attachment_name=payload.attachment_name,
    )
    return AgentResponseGenerateResponse(
        agent_id=agent.id or "",
        agent_name=agent.name,
        chat_id=chat.id or "",
        content=content,
        memory_summary=factory.agent_service.parse_memory_summary(memory_summary),
    )


@router.get("/{agent_id}/response/history", response_model=AgentResponseHistoryResponse)
async def get_agent_response_history(
    agent_id: str,
    chat_id: str | None = None,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    agent, chat, messages, total_message_count = await factory.agent_service.get_agent_response_history(
        agent_id,
        current_user,
        chat_id=chat_id,
    )
    return AgentResponseHistoryResponse(
        agent_id=agent.id or "",
        agent_name=agent.name,
        chat_id=chat.id if chat else None,
        memory_summary=factory.agent_service.parse_memory_summary(
            chat.memory if chat else None
        ),
        total_message_count=total_message_count,
        has_more_messages=total_message_count > len(messages),
        messages=[
            AgentResponseMessage.model_validate(
                {
                    **message.model_dump(),
                    "id": message.id or "",
                },
            )
            for message in messages
        ],
    )

@router.get("/{agent_id}/response/pages", response_model=list[AgentResponsePage])
async def list_agent_response_pages(
    agent_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    pages = await factory.agent_service.list_agent_response_pages(agent_id, current_user)
    return [
        AgentResponsePage(
            id=chat.id or "",
            agent_id=chat.agent_id,
            agent_name=chat.agent_name,
            title=chat.title,
            memory_summary=factory.agent_service.parse_memory_summary(chat.memory or chat.summary),
            message_count=message_count,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
        )
        for chat, message_count in pages
    ]


@router.post(
    "/{agent_id}/response/pages",
    response_model=AgentResponsePage,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_response_page(
    agent_id: str,
    payload: AgentResponsePageCreateRequest,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    chat = await factory.agent_service.create_agent_response_page(
        agent_id,
        current_user,
        title=payload.title,
    )
    return AgentResponsePage(
        id=chat.id or "",
        agent_id=chat.agent_id,
        agent_name=chat.agent_name,
        title=chat.title,
        memory_summary=factory.agent_service.parse_memory_summary(chat.memory or chat.summary),
        message_count=0,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
    )


@router.delete("/{agent_id}/response/pages/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_response_page(
    agent_id: str,
    chat_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    await factory.chat_service.delete_chat(agent_id, chat_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{agent_id}/chats", response_model=list[ChatResponse])
async def list_chats(
    agent_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.chat_service.list_chats(agent_id, current_user)


@router.post("/{agent_id}/chats", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    agent_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.chat_service.create_chat(agent_id, current_user)


@router.get("/{agent_id}/chat/messages", response_model=list[MessageResponse])
async def list_default_chat_messages(
    agent_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    chat = await factory.chat_service.get_or_create_chat(agent_id, current_user)
    return await factory.chat_service.list_messages(chat.id or "")


@router.get("/{agent_id}/chats/{chat_id}/messages", response_model=list[MessageResponse])
async def list_chat_messages(
    agent_id: str,
    chat_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.chat_service.list_chat_messages(agent_id, chat_id, current_user)


@router.post("/{agent_id}/chat/messages", response_model=ChatSendResponse)
async def send_default_chat_message(
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
    return ChatSendResponse(
        user_message=MessageResponse.model_validate(user_message),
        assistant_message=MessageResponse.model_validate(assistant_message),
    )


@router.post("/{agent_id}/chats/{chat_id}/messages", response_model=ChatSendResponse)
async def send_chat_message(
    agent_id: str,
    chat_id: str,
    payload: MessageCreate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    user_message, assistant_message = await factory.chat_service.send_chat_message(
        agent_id,
        chat_id,
        current_user,
        payload.content,
    )
    return ChatSendResponse(
        user_message=MessageResponse.model_validate(user_message),
        assistant_message=MessageResponse.model_validate(assistant_message),
    )


@router.patch("/{agent_id}/chat/messages/{message_id}", response_model=ChatSendResponse)
async def update_default_chat_message(
    agent_id: str,
    message_id: str,
    payload: MessageUpdate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    user_message, assistant_message = await factory.chat_service.update_user_message(
        agent_id,
        current_user,
        message_id,
        payload.content,
    )
    return ChatSendResponse(
        user_message=MessageResponse.model_validate(user_message),
        assistant_message=MessageResponse.model_validate(assistant_message),
    )


@router.patch("/{agent_id}/chats/{chat_id}/messages/{message_id}", response_model=ChatSendResponse)
async def update_chat_message(
    agent_id: str,
    chat_id: str,
    message_id: str,
    payload: MessageUpdate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    user_message, assistant_message = await factory.chat_service.update_chat_user_message(
        agent_id,
        chat_id,
        current_user,
        message_id,
        payload.content,
    )
    return ChatSendResponse(
        user_message=MessageResponse.model_validate(user_message),
        assistant_message=MessageResponse.model_validate(assistant_message),
    )


@router.delete("/{agent_id}/chat/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_default_chat_message(
    agent_id: str,
    message_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    await factory.chat_service.delete_message(agent_id, current_user, message_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{agent_id}/chats/{chat_id}/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chat_message(
    agent_id: str,
    chat_id: str,
    message_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    await factory.chat_service.delete_chat_message(agent_id, chat_id, current_user, message_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/response/latest", response_model=AgentResponseHistoryResponse)
async def get_latest_agent_response_history(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    agent, chat, messages = await factory.agent_service.get_latest_agent_response_history(
        current_user,
    )
    return AgentResponseHistoryResponse(
        agent_id=agent.id or "",
        agent_name=agent.name,
        chat_id=chat.id,
        memory_summary=factory.agent_service.parse_memory_summary(chat.memory or chat.summary),
        messages=[
            AgentResponseMessage.model_validate(
                {
                    **message.model_dump(),
                    "id": message.id or "",
                },
            )
            for message in messages
        ],
    )


@router.delete("/{agent_id}/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    agent_id: str,
    chat_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    await factory.chat_service.delete_chat(agent_id, chat_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{agent_id}/response/messages/{message_id}",
    response_model=AgentResponseHistoryResponse,
)
async def update_agent_response_message(
    agent_id: str,
    message_id: str,
    payload: AgentResponseGenerateRequest,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    agent, chat, messages = await factory.agent_service.update_agent_response_message(
        agent_id,
        current_user,
        message_id,
        payload.content,
    )
    return AgentResponseHistoryResponse(
        agent_id=agent.id or "",
        agent_name=agent.name,
        chat_id=chat.id,
        memory_summary=factory.agent_service.parse_memory_summary(chat.memory or chat.summary),
        messages=[
            AgentResponseMessage.model_validate(
                {
                    **message.model_dump(),
                    "id": message.id or "",
                },
            )
            for message in messages
        ],
    )


@router.delete(
    "/{agent_id}/response/messages/{message_id}",
    response_model=AgentResponseHistoryResponse,
)
async def delete_agent_response_message(
    agent_id: str,
    message_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    agent, chat, messages = await factory.agent_service.delete_agent_response_message(
        agent_id,
        current_user,
        message_id,
    )
    return AgentResponseHistoryResponse(
        agent_id=agent.id or "",
        agent_name=agent.name,
        chat_id=chat.id,
        memory_summary=factory.agent_service.parse_memory_summary(chat.memory or chat.summary),
        messages=[
            AgentResponseMessage.model_validate(
                {
                    **message.model_dump(),
                    "id": message.id or "",
                },
            )
            for message in messages
        ],
    )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.agent_service.get_agent(agent_id, current_user)


@router.patch("/{agent_id}", response_model=ApiResponse[AgentResponse])
async def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    agent = await factory.agent_service.update_agent(agent_id, payload, current_user)
    return ApiResponse(
        message="Agent updated successfully",
        data=agent,
    )


@router.put("/{agent_id}", response_model=ApiResponse[AgentResponse])
async def replace_agent(
    agent_id: str,
    payload: AgentUpdate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    agent = await factory.agent_service.update_agent(agent_id, payload, current_user)
    return ApiResponse(
        message="Agent updated successfully",
        data=agent,
    )


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    await factory.agent_service.delete_agent(agent_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
