from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .chat import ChatCompletion
from .model_policies import ModelPolicyMode


class RuntimePolicyMode(StrEnum):
    OBSERVE = "observe"
    WARN = "warn"
    ENFORCE = "enforce"


class RuntimeDecision(StrEnum):
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"
    CANCEL = "cancel"


class RecoveryStrategy(StrEnum):
    RETRY_MODIFIED = "retry_modified"
    MODEL_HANDOFF = "model_handoff"
    MANUAL_RESUME = "manual_resume"
    STOP = "stop"


class RuntimeExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task: str = Field(min_length=1, max_length=2_000)
    model: str = Field(min_length=1, max_length=128)
    provider: str = Field(default="custom", min_length=1, max_length=64)
    application_slug: str | None = Field(default=None, min_length=1, max_length=63)
    agent_slug: str | None = Field(default=None, min_length=1, max_length=63)
    repeat_threshold: int = Field(default=3, ge=2, le=20)
    window_size: int = Field(default=12, ge=4, le=100)
    policy_mode: RuntimePolicyMode = RuntimePolicyMode.ENFORCE


class RuntimeExecutionCreated(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_id: UUID
    trace_id: str
    status: str
    repeat_threshold: int
    policy_mode: RuntimePolicyMode


class RuntimeActionCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(default="tool", pattern="^(tool|model)$")
    name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)


class RuntimeActionDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_id: UUID
    action_id: UUID
    decision: RuntimeDecision
    operation_fingerprint: str
    occurrence: int
    threshold: int
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    checkpoint_id: UUID | None = None


class RuntimeActionCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str = Field(default="completed", pattern="^(completed|failed)$")
    result: Any = None
    progress: bool
    summary: str | None = Field(default=None, max_length=500)


class RuntimeActionCompleted(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_id: UUID
    action_id: UUID
    status: str
    result_fingerprint: str
    progress: bool


class RuntimePreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(ge=0)
    requested_output_tokens: int = Field(ge=1, le=32_768)
    estimated_cost: Decimal = Field(default=Decimal(0), ge=0)


class RuntimeBudgetProjection(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_id: UUID
    name: str
    scope_type: str
    period_type: str
    mode: RuntimePolicyMode
    consumed_requests: int = Field(ge=0)
    consumed_tokens: int = Field(ge=0)
    consumed_cost: Decimal = Field(ge=0)
    projected_requests: int = Field(ge=0)
    projected_tokens: int = Field(ge=0)
    projected_cost: Decimal = Field(ge=0)
    max_requests: int | None = None
    max_tokens: int | None = None
    max_cost: Decimal | None = None
    exceeded: bool


class RuntimeModelPolicyProjection(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_id: UUID
    provider: str
    model: str
    mode: ModelPolicyMode
    projected_tokens: int = Field(ge=0)
    token_limit: int | None = None
    triggered: bool


class RuntimePreflightResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_id: UUID
    decision: RuntimeDecision
    reason: str
    provider: str
    model: str
    input_tokens: int
    reserved_output_tokens: int
    safety_margin_tokens: int
    projected_context_tokens: int
    context_window_tokens: int
    context_remaining_tokens: int
    context_utilization: float = Field(ge=0)
    budgets: list[RuntimeBudgetProjection] = Field(default_factory=list)
    model_policy: RuntimeModelPolicyProjection | None = None
    checkpoint_id: UUID | None = None


class ContinuityPacket(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str = "1.0"
    task: str
    source_execution_id: UUID
    source_provider: str = "custom"
    source_model: str
    completed_work: list[str] = Field(default_factory=list)
    failed_operation: dict[str, Any] = Field(default_factory=dict)
    reason_for_intervention: str
    recommended_action: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RuntimeCheckpoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    execution_id: UUID
    status: str
    content_fingerprint: str
    packet: ContinuityPacket
    created_at: datetime
    consumed_at: datetime | None = None


class RuntimeIntervention(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_id: UUID
    execution_status: str
    policy_code: str
    policy_mode: RuntimePolicyMode
    outcome: str
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    decided_at: datetime
    checkpoint: RuntimeCheckpoint | None = None


class RuntimeRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: RecoveryStrategy
    target_provider: str | None = Field(default=None, min_length=1, max_length=64)
    target_model: str | None = Field(default=None, min_length=1, max_length=128)
    modified_arguments: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_handoff_target(self) -> "RuntimeRecoveryRequest":
        if (
            self.strategy is RecoveryStrategy.RETRY_MODIFIED
            and not self.modified_arguments
        ):
            raise ValueError("modified_arguments are required for retry_modified")
        if self.strategy is RecoveryStrategy.MODEL_HANDOFF and (
            self.target_provider is None or self.target_model is None
        ):
            raise ValueError(
                "target_provider and target_model are required for model_handoff"
            )
        return self


class RuntimeRecoveryResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_execution_id: UUID
    strategy: RecoveryStrategy
    status: str
    resumed_execution_id: UUID | None = None
    target_provider: str | None = None
    target_model: str | None = None
    checkpoint: RuntimeCheckpoint
    message: str
    completion: ChatCompletion | None = None


class RuntimeCancellationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_id: UUID
    status: str
    checkpoint_id: UUID | None = None
