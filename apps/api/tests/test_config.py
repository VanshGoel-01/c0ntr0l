import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_settings_parse_comma_separated_cors_origins() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:password@localhost/database",
        redis_url="redis://localhost:6379/0",
        cors_origins="http://localhost:3000, http://localhost:3001",
    )

    assert settings.cors_origin_list == [
        "http://localhost:3000",
        "http://localhost:3001",
    ]


def test_settings_reject_wildcard_cors_with_credentials() -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://user:password@localhost/database",
            redis_url="redis://localhost:6379/0",
            cors_origins="*",
        )


def test_production_rejects_development_security_defaults() -> None:
    with pytest.raises(ValidationError, match="API_KEY_PEPPER"):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql+asyncpg://user:password@localhost/database",
            redis_url="redis://localhost:6379/0",
        )


def test_production_requires_demo_scenarios_to_be_disabled() -> None:
    with pytest.raises(ValidationError, match="ALLOW_DEMO_SCENARIOS"):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql+asyncpg://user:password@localhost/database",
            redis_url="redis://localhost:6379/0",
            api_key_pepper="production-test-pepper",
        )
