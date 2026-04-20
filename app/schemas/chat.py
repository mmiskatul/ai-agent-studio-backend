from datetime import datetime

from pydantic import BaseModel, Field


class ChatResponse(BaseModel):
    id: str
    user_id: str
    agent_id: str
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)


class MessageResponse(BaseModel):
    id: str
    chat_id: str
    sender_type: str
    content: str
    created_at: datetime
    updated_at: datetime


class ChatSendResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
