from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApplicationContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    slug: str
    name: str
    environment: str
    status: str


class BudgetPolicyContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str
    scope_type: str
    scope_id: UUID
    period_type: str
    mode: str
    max_requests: int | None
    max_tokens: int | None
    max_cost: Decimal | None
    currency: str
    is_enabled: bool


class WorkspaceContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    organization_id: UUID
    organization_name: str
    project_id: UUID
    project_slug: str
    project_name: str
    applications: list[ApplicationContext] = Field(default_factory=list)
    budgets: list[BudgetPolicyContext] = Field(default_factory=list)
    requests_24h: int = Field(ge=0)
    tokens_24h: int = Field(ge=0)
    cost_24h: Decimal = Field(ge=0)
