from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ControlEventType(StrEnum):
    EXECUTION_STARTED = "execution.started"
    EXECUTION_UPDATED = "execution.updated"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"
    EXECUTION_BLOCKED = "execution.blocked"
    EXECUTION_CANCELLED = "execution.cancelled"
    INCIDENT_UPDATED = "incident.updated"
    RECOVERY_UPDATED = "recovery.updated"


class ControlEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^\d+-\d+$", max_length=64)
    type: ControlEventType
    execution_id: UUID | None = None
    occurred_at: datetime


class SpanSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    parent_span_id: UUID | None = None
    sequence_no: int
    kind: str
    name: str
    tool_name: str | None = None
    status: str
    duration_ms: int | None
    error_code: str | None
    started_at: datetime
    completed_at: datetime | None
    attributes: dict[str, object] = Field(default_factory=dict)


class UsageSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_type: str
    provider: str | None
    model: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_amount: Decimal
    currency: str
    latency_ms: int | None
    observed_at: datetime


class ExecutionSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    request_id: str | None = None
    project_id: UUID | None = None
    project_name: str | None = None
    application_id: UUID | None = None
    application_name: str | None = None
    agent_id: UUID | None = None
    agent_name: str | None = None
    status: str
    requested_model: str
    active_provider: str | None
    active_model: str | None
    is_streaming: bool
    input_fingerprint: str | None
    output_fingerprint: str | None
    final_reason: str | None
    error_code: str | None
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    span_count: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    total_cost: Decimal = Field(ge=0)
    metadata: dict[str, object] = Field(default_factory=dict)


class ExecutionDetail(ExecutionSummary):
    spans: list[SpanSummary]
    usage: list[UsageSummary]
