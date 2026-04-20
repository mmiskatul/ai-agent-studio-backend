from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_service_factory
from app.factories.service_factory import ServiceFactory
from app.models.user import UserDocument
from app.schemas.chat import ChatResponse, ChatSendResponse, MessageCreate, MessageResponse

router = APIRouter()


@router.get("/{agent_id}/chat", response_model=ChatResponse)
async def get_or_create_chat(
    agent_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.chat_service.get_or_create_chat(agent_id, current_user)


@router.get("/{agent_id}/chat/messages", response_model=list[MessageResponse])
async def list_messages(
    agent_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    chat = await factory.chat_service.get_or_create_chat(agent_id, current_user)
    return await factory.chat_service.list_messages(chat.id or "")


@router.post("/{agent_id}/chat/messages", response_model=ChatSendResponse)
async def send_message(
    agent_id: str,
    payload: MessageCreate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
) -> ChatSendResponse:
    user_message, assistant_message = await factory.chat_service.send_message(
        agent_id,
        current_user,
        payload.content,
    )
    return ChatSendResponse(user_message=user_message, assistant_message=assistant_message)
