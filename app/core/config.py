import json
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

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
    openai_agent_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    cloudinary_folder: str = "agenthub/knowledge"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
