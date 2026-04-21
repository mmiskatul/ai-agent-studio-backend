from datetime import datetime

from pydantic import BaseModel, Field


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


class LLMEngineOption(BaseModel):
    value: str
    label: str


class LLMEngineOptionsResponse(BaseModel):
    default_engine: str
    engines: list[LLMEngineOption]


class AgentDescriptionGenerateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class AgentDescriptionGenerateResponse(BaseModel):
    short_description: str


class AgentSystemPromptGenerateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    short_description: str = Field(min_length=1, max_length=500)
    category_tag: str | None = None
    base_template: str | None = None


class AgentSystemPromptGenerateResponse(BaseModel):
    system_prompt: str


class AgentWelcomeMessageGenerateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    short_description: str = Field(min_length=1, max_length=500)
    category_tag: str | None = None
    base_template: str | None = None


class AgentWelcomeMessageGenerateResponse(BaseModel):
    welcome_message: str


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
