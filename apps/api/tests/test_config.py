import pytest
from pydantic import ValidationError

from companion.config import Settings


def test_production_configuration_rejects_local_or_missing_secrets() -> None:
    with pytest.raises(ValidationError, match="Invalid deployed configuration"):
        Settings(app_env="production")


def test_production_configuration_accepts_required_external_services() -> None:
    settings = Settings(
        app_env="production",
        database_url="postgresql://user:password@db:5432/companion",
        redis_url="redis://redis:6379/0",
        llm_provider="xai",
        xai_api_key="xai-secret",
        internal_api_key="a" * 40,
        cors_origins=["https://companion.example"],
    )

    assert settings.database_url.startswith("postgresql+psycopg://")
