from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role: str = Field(default="AI Agent", min_length=1)
    description: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    tools: list[str] = Field(default_factory=list)
    model: str = Field(min_length=1)
    temperature: float = Field(default=0.7, ge=0, le=2)
    is_active: bool = True
