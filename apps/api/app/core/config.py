from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: str = "http://localhost:3000"
    database_url: str
    redis_url: str
    provider_base_url: str = "http://127.0.0.1:8002"
    provider_timeout_seconds: float = Field(default=10.0, ge=0.1, le=120.0)
    api_key_pepper: SecretStr = SecretStr("local-development-only-change-me")
    allow_demo_scenarios: bool = True
    service_name: str = "c0ntr0l-api"
    service_version: str = "0.1.0"

    @model_validator(mode="after")
    def reject_insecure_production_defaults(self) -> "Settings":
        if "*" in self.cors_origin_list:
            raise ValueError(
                "CORS_ORIGINS cannot contain a wildcard when credentials are enabled"
            )
        if self.app_env == "production":
            if (
                self.api_key_pepper.get_secret_value()
                == "local-development-only-change-me"
            ):
                raise ValueError("API_KEY_PEPPER must be changed in production")
            if self.allow_demo_scenarios:
                raise ValueError("ALLOW_DEMO_SCENARIOS must be false in production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
