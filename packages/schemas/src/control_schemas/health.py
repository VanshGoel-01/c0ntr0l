from pydantic import BaseModel, ConfigDict, Field

from .common import DependencyStatus, HealthStatus


class DependencyHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: DependencyStatus
    detail: str | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: HealthStatus
    service: str = "c0ntr0l-api"
    version: str
    dependencies: dict[str, DependencyHealth] = Field(default_factory=dict)
