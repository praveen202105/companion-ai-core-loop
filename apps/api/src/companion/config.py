from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
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
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_chat_model: str = "openai/gpt-oss-120b"
    groq_extraction_model: str = "openai/gpt-oss-20b"
    groq_judge_model: str = "openai/gpt-oss-20b"
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

    @model_validator(mode="after")
    def validate_deployed_configuration(self) -> Settings:
        if self.app_env not in {"staging", "production"}:
            return self
        missing: list[str] = []
        if not self.database_url.startswith("postgresql+psycopg://"):
            missing.append("DATABASE_URL must use PostgreSQL")
        if not self.redis_url:
            missing.append("REDIS_URL")
        provider_is_configured = (
            self.llm_provider == "xai" and bool(self.xai_api_key)
        ) or (self.llm_provider == "groq" and bool(self.groq_api_key))
        if not provider_is_configured:
            missing.append("LLM_PROVIDER with its matching API key")
        if len(self.internal_api_key) < 32 or "change-me" in self.internal_api_key:
            missing.append("a strong INTERNAL_API_KEY")
        if not self.cors_origins or "*" in self.cors_origins:
            missing.append("restrictive CORS_ORIGINS")
        if missing:
            raise ValueError("Invalid deployed configuration: " + ", ".join(missing))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
