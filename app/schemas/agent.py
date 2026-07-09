from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AgentLanguage = Literal["EN", "DE", "RU"]
AgentStatus = Literal["enabled", "disabled"]


class AgentBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = Field(default=None, alias="_id")
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    purpose: str = Field(default="")
    description: str | None = None
    knowledge_text: str | None = None
    language: AgentLanguage = "EN"
    template_type: str | None = None
    template_id: str | None = None
    category_tag: str | None = None
    system_prompt: str = Field(min_length=1)
    welcome_message: str | None = None
    llm_engine: str = "gpt-4o"
    model: str | None = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    status: AgentStatus = "enabled"
    tools: list[str] = Field(default_factory=list)
    routing_keywords: list[str] = Field(default_factory=list)
    priority: int = Field(default=100, ge=0)
    is_active: bool = True


class AgentCreate(AgentBase):
    pass


class AgentAICreate(BaseModel):
    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    role: str | None = Field(default=None, min_length=1)
    template_type: str | None = None
    template_id: str | None = None
    language: AgentLanguage = "EN"
    status: AgentStatus = "enabled"
    instructions: str | None = None
    tone: str = "professional"


class AgentBuilderCreate(BaseModel):
    name: str = Field(min_length=1)
    short_description: str = Field(min_length=1)
    base_template: str = "blank"
    template_id: str | None = None
    category_tag: str | None = None
    language: AgentLanguage = "EN"
    system_prompt: str = Field(min_length=1)
    welcome_message: str | None = None
    llm_engine: str = "gpt-4o"
    temperature: float = Field(default=0.7, ge=0, le=2)
    status: AgentStatus = "enabled"


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
    content: str = ""
    chat_id: str | None = None
    attachment_text: str | None = None
    attachment_name: str | None = None

    @model_validator(mode="after")
    def validate_has_content(self):
        if self.content.strip() or (self.attachment_text or "").strip():
            return self
        raise ValueError("Either content or attachment_text is required")


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
    total_message_count: int = 0
    has_more_messages: bool = False


class AgentResponsePageCreateRequest(BaseModel):
    title: str | None = None


class AgentResponsePage(BaseModel):
    id: str
    agent_id: str
    agent_name: str | None = None
    title: str | None = None
    memory_summary: MemorySummary
    message_count: int
    created_at: datetime
    updated_at: datetime


class AgentKnowledgeUploadResponse(BaseModel):
    file_name: str
    content_type: str
    extracted_text: str
    character_count: int


class AgentKnowledgeExtractionJobResponse(BaseModel):
    job_id: str
    status: str
    file_name: str
    content_type: str
    character_count: int = 0
    extracted_text: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class AgentRegistryRebuildResponse(BaseModel):
    total_agents: int
    active_agents: int
    agent_ids: list[str]


class AgentDescriptionGenerateRequest(BaseModel):
    name: str = Field(min_length=1)
    role: str | None = Field(default=None, min_length=1)


class AgentDescriptionGenerateResponse(BaseModel):
    short_description: str


class AgentSystemPromptGenerateRequest(BaseModel):
    name: str = Field(min_length=1)
    short_description: str = Field(min_length=1)
    category_tag: str | None = None
    base_template: str | None = None


class AgentSystemPromptGenerateResponse(BaseModel):
    system_prompt: str


class AgentWelcomeMessageGenerateRequest(BaseModel):
    name: str = Field(min_length=1)
    short_description: str = Field(min_length=1)
    category_tag: str | None = None
    base_template: str | None = None


class AgentWelcomeMessageGenerateResponse(BaseModel):
    welcome_message: str


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    role: str | None = Field(default=None, min_length=1)
    purpose: str | None = Field(default=None, min_length=1)
    description: str | None = None
    language: AgentLanguage | None = None
    template_type: str | None = None
    template_id: str | None = None
    category_tag: str | None = None
    system_prompt: str | None = Field(default=None, min_length=1)
    welcome_message: str | None = None
    llm_engine: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    status: AgentStatus | None = None
    tools: list[str] | None = None
    routing_keywords: list[str] | None = None
    priority: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class AgentResponse(AgentBase):
    id: str
    user_id: str
    owner_user_id: str
    queries_30d: int = 0
    created_at: datetime
    updated_at: datetime
