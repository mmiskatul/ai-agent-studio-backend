import json
import os
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AgentHub API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    backend_cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    mongodb_uri: str = "mongodb+srv://<username>:<password>@<cluster-url>/agenthub?retryWrites=true&w=majority"
    mongodb_db_name: str = "agenthub"

    jwt_secret_key: str = "change-this-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_session_token_expire_days: int = 30
    email_code_expire_minutes: int = 10

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "AgentHub"
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False

    openai_api_key: str = ""
    openai_agent_model: str = ""
    llm_engine_options: Annotated[list[dict[str, str]], NoDecode] = Field(
        default_factory=lambda: [
            {"value": "gpt-4o-mini", "label": "GPT-4o mini"},
            {"value": "gpt-4.1-mini", "label": "GPT-4.1 mini"},
            {"value": "gpt-4.1", "label": "GPT-4.1"},
            {"value": "gpt-4o", "label": "GPT-4o"},
        ]
    )

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                parsed_value = json.loads(value)
                if isinstance(parsed_value, list):
                    return parsed_value
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("llm_engine_options", mode="before")
    @classmethod
    def parse_llm_engine_options(cls, value: str | list[dict[str, str]]) -> list[dict[str, str]]:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            parsed_value = json.loads(value)
            if isinstance(parsed_value, list):
                return parsed_value
        return value

    @property
    def default_llm_engine(self) -> str:
        if self.openai_agent_model:
            return self.openai_agent_model
        if self.llm_engine_options:
            return self.llm_engine_options[0]["value"]
        return ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

if settings.openai_api_key:
    os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
if settings.openai_agent_model:
    os.environ.setdefault("OPENAI_AGENT_MODEL", settings.openai_agent_model)
