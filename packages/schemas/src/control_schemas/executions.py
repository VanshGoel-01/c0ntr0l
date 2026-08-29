from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SpanSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    sequence_no: int
    kind: str
    name: str
    status: str
    duration_ms: int | None
    error_code: str | None
    started_at: datetime
    completed_at: datetime | None


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


class ExecutionDetail(ExecutionSummary):
    spans: list[SpanSummary]
    usage: list[UsageSummary]
