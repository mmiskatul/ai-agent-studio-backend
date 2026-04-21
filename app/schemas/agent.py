from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.knowledge import KnowledgeResponse


class AgentBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=160)
    purpose: str = Field(min_length=1, max_length=500)
    template_type: str | None = None
    category_tag: str | None = None
    system_prompt: str = Field(min_length=1)
    welcome_message: str | None = None
    llm_engine: str = "gpt-4o"
    temperature: float = Field(default=0.7, ge=0, le=2)
    status: str = "active"


class AgentCreate(AgentBase):
    pass


class AgentAICreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=500)
    role: str | None = Field(default=None, min_length=1, max_length=160)
    template_type: str | None = None
    status: str = "active"
    instructions: str | None = None
    tone: str = "professional"


class AgentBuilderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    short_description: str = Field(min_length=1, max_length=500)
    base_template: str = "blank"
    category_tag: str | None = None
    system_prompt: str = Field(min_length=1)
    welcome_message: str | None = None
    llm_engine: str = "gpt-4o"
    temperature: float = Field(default=0.7, ge=0, le=2)
    status: str = "active"


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, min_length=1, max_length=160)
    purpose: str | None = Field(default=None, min_length=1, max_length=500)
    template_type: str | None = None
    category_tag: str | None = None
    system_prompt: str | None = Field(default=None, min_length=1)
    welcome_message: str | None = None
    llm_engine: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    status: str | None = None


class AgentResponse(AgentBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime


class AgentKnowledgeCreateResponse(BaseModel):
    agent: AgentResponse
    knowledge: KnowledgeResponse | None = None
