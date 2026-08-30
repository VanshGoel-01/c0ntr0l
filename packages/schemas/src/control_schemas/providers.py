from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ProviderAvailability(StrEnum):
    OPERATIONAL = "operational"
    UNAVAILABLE = "unavailable"


class ProviderModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str = Field(min_length=1, max_length=128)


class ProviderModelList(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    data: list[ProviderModel] = Field(max_length=1_000)


class ProviderSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$")
    status: ProviderAvailability
    models: list[str] = Field(max_length=1_000)


class ProviderCatalog(BaseModel):
    model_config = ConfigDict(frozen=True)

    checked_at: datetime
    providers: list[ProviderSummary]
