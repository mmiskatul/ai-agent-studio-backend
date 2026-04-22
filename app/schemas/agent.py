from datetime import datetime

from pydantic import BaseModel, Field


class AgentBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=160)
    purpose: str = Field(min_length=1, max_length=1500)
    description: str | None = None
    template_type: str | None = None
    category_tag: str | None = None
    system_prompt: str = Field(min_length=1)
    welcome_message: str | None = None
    llm_engine: str = "gpt-4o"
    model: str | None = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    status: str = "active"
    tools: list[str] = Field(default_factory=list)
    is_active: bool = True


class AgentCreate(AgentBase):
    pass


class AgentAICreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=1500)
    role: str | None = Field(default=None, min_length=1, max_length=160)
    template_type: str | None = None
    status: str = "active"
    instructions: str | None = None
    tone: str = "professional"


class AgentBuilderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    short_description: str = Field(min_length=1, max_length=1500)
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


class AgentConfigResponse(BaseModel):
    id: str
    name: str
    role: str
    description: str
    system_prompt: str
    tools: list[str]
    model: str
    temperature: float
    is_active: bool


class ToolResponse(BaseModel):
    name: str
    description: str


class AgentRouteRequest(BaseModel):
    task: str = Field(min_length=1)
    agent_key: str | None = None


class AgentRouteResponse(BaseModel):
    agent_id: str
    agent_name: str
    description: str
    tools: list[str]


class AgentResponseGenerateRequest(BaseModel):
    content: str = Field(min_length=1)
    chat_id: str | None = None


class MemorySummary(BaseModel):
    title: str = ""
    description: str = ""


class AgentResponseGenerateResponse(BaseModel):
    agent_id: str
    agent_name: str
    chat_id: str
    content: str
    memory_summary: MemorySummary


class AgentResponseMessage(BaseModel):
    id: str
    chat_id: str
    sender_type: str
    content: str
    created_at: datetime
    updated_at: datetime


class AgentResponseHistoryResponse(BaseModel):
    agent_id: str
    agent_name: str
    chat_id: str | None = None
    memory_summary: MemorySummary
    messages: list[AgentResponseMessage]


class AgentResponsePageCreateRequest(BaseModel):
    title: str | None = None


class AgentResponsePage(BaseModel):
    id: str
    agent_id: str
    title: str | None = None
    memory_summary: MemorySummary
    message_count: int
    created_at: datetime
    updated_at: datetime


class AgentRegistryRebuildResponse(BaseModel):
    total_agents: int
    active_agents: int
    agent_ids: list[str]


class AgentDescriptionGenerateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class AgentDescriptionGenerateResponse(BaseModel):
    short_description: str


class AgentSystemPromptGenerateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    short_description: str = Field(min_length=1, max_length=1500)
    category_tag: str | None = None
    base_template: str | None = None


class AgentSystemPromptGenerateResponse(BaseModel):
    system_prompt: str


class AgentWelcomeMessageGenerateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    short_description: str = Field(min_length=1, max_length=1500)
    category_tag: str | None = None
    base_template: str | None = None


class AgentWelcomeMessageGenerateResponse(BaseModel):
    welcome_message: str


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, min_length=1, max_length=160)
    purpose: str | None = Field(default=None, min_length=1, max_length=1500)
    description: str | None = None
    template_type: str | None = None
    category_tag: str | None = None
    system_prompt: str | None = Field(default=None, min_length=1)
    welcome_message: str | None = None
    llm_engine: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    status: str | None = None
    tools: list[str] | None = None
    is_active: bool | None = None


class AgentResponse(AgentBase):
    id: str
    user_id: str
    queries_30d: int = 0
    created_at: datetime
    updated_at: datetime
