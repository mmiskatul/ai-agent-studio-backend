from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    agent_id: str
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
