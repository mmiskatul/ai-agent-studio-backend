from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    agent_id: str
    current_agent_id: str | None = None
    session_id: str | None = None
    title: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)


class MessageUpdate(BaseModel):
    content: str = Field(min_length=1)


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chat_id: str
    sender_type: str
    content: str
    created_at: datetime
    updated_at: datetime


class ChatSendResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse


class ChatSendRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None
    chat_id: str | None = None
    agent_id: str | None = None


class RoutedAgentResponse(BaseModel):
    id: str
    name: str
    role: str


class ChatStructuredResponse(BaseModel):
    session_id: str
    chat_id: str
    agent: RoutedAgentResponse
    system_summary: str
    response: str
    markdown: str
    render_mode: str
    routing_reason: str
    memory_updated: bool
    metadata: dict


class ChatHistoryResponse(BaseModel):
    session_id: str
    chats: list[ChatResponse]
    messages: list[MessageResponse]
