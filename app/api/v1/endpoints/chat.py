from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_service_factory
from app.factories.service_factory import ServiceFactory
from app.models.user import UserDocument
from app.schemas.chat import (
    ChatHistoryResponse,
    ChatResponse,
    ChatSendRequest,
    ChatStructuredResponse,
    MessageResponse,
)

router = APIRouter()


@router.post("/send", response_model=ChatStructuredResponse)
async def send_chat_message(
    payload: ChatSendRequest,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.multi_chat_service.send(
        user_id=current_user.id or "",
        message=payload.message,
        session_id=payload.session_id,
        chat_id=payload.chat_id,
        agent_id=payload.agent_id,
    )


@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    chats, messages = await factory.multi_chat_service.history(
        user_id=current_user.id or "",
        session_id=session_id,
    )
    return ChatHistoryResponse(
        session_id=session_id,
        chats=[ChatResponse.model_validate(chat) for chat in chats],
        messages=[MessageResponse.model_validate(message) for message in messages],
    )
