from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    database_url: str = "sqlite:///./data/companion.db"
    redis_url: str | None = None
    xai_api_key: str | None = None
    xai_base_url: str = "https://api.x.ai/v1"
    xai_chat_model: str = "grok-4.3"
    xai_extraction_model: str = "grok-4.3"
    xai_judge_model: str = "grok-4.6"
    llm_provider: str = "fake"
    embedding_provider: str = "hash"
    internal_api_key: str = "local-internal-key-change-me"
    cors_origins: list[str] = ["http://localhost:3000"]
    session_retention_days: int = Field(default=30, ge=1, le=365)
    chat_rate_limit_per_minute: int = Field(default=10, ge=1)
    chat_rate_limit_per_day: int = Field(default=100, ge=1)

    @field_validator("database_url")
    @classmethod
    def normalize_postgres_driver(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
