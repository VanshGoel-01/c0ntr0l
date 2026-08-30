from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ModelPolicyMode(StrEnum):
    OBSERVE = "observe"
    WARN = "warn"
    BLOCK = "block"


class ModelPolicyUpsert(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    provider: str = Field(
        min_length=1,
        max_length=63,
        pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$",
    )
    model: str = Field(min_length=1, max_length=255)
    mode: ModelPolicyMode = ModelPolicyMode.OBSERVE
    token_limit: int | None = Field(default=None, gt=0)


class ModelPolicyContext(ModelPolicyUpsert):
    model_config = ConfigDict(frozen=True)

    id: UUID
    project_id: UUID
    created_at: datetime
    updated_at: datetime
