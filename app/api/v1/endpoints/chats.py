from fastapi import APIRouter, Depends, Response, status

from app.dependencies import get_current_user, get_service_factory
from app.factories.service_factory import ServiceFactory
from app.models.user import UserDocument
from app.schemas.chat import (
    ChatResponse,
    ChatSendResponse,
    MessageCreate,
    MessageResponse,
    MessageUpdate,
)

router = APIRouter()


@router.get("/{agent_id}/chat", response_model=ChatResponse)
async def get_or_create_chat(
    agent_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.chat_service.get_or_create_chat(agent_id, current_user)


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
async def list_messages(
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
) -> ChatSendResponse:
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
async def update_message(
    agent_id: str,
    message_id: str,
    payload: MessageUpdate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
) -> ChatSendResponse:
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
) -> ChatSendResponse:
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
async def delete_message(
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


@router.delete("/{agent_id}/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    agent_id: str,
    chat_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    await factory.chat_service.delete_chat(agent_id, chat_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
