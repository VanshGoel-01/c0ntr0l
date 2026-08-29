from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MOCK_PROVIDER_",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = "c0ntr0l-mock-provider"
    service_version: str = "0.1.0"
    default_model: str = "mock-gpt"
    timeout_delay_seconds: float = Field(default=5.0, ge=0.01, le=60.0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
