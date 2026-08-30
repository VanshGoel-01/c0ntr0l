from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from control_schemas import (
    RuntimeBudgetProjection,
    RuntimeDecision,
    RuntimePolicyMode,
    RuntimePreflightRequest,
)


@dataclass(frozen=True, slots=True)
class PreflightExecution:
    execution_id: UUID
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    policy_id: UUID
    name: str
    scope_type: str
    period_type: str
    mode: RuntimePolicyMode
    consumed_requests: int
    consumed_tokens: int
    consumed_cost: Decimal
    max_requests: int | None
    max_tokens: int | None
    max_cost: Decimal | None


@dataclass(frozen=True, slots=True)
class PreflightAssessment:
    decision: RuntimeDecision
    mode: RuntimePolicyMode
    reason: str
    projected_context_tokens: int
    context_remaining_tokens: int
    context_utilization: float
    budgets: list[RuntimeBudgetProjection]
    blocking_policy_id: UUID | None = None


def evaluate_preflight(
    request: RuntimePreflightRequest,
    budgets: list[BudgetSnapshot],
    *,
    context_window_tokens: int,
    safety_margin_tokens: int,
    warning_utilization: float,
) -> PreflightAssessment:
    projected_context = (
        request.input_tokens
        + request.requested_output_tokens
        + safety_margin_tokens
    )
    remaining = max(0, context_window_tokens - projected_context)
    utilization = projected_context / context_window_tokens
    projections = [_project_budget(snapshot, request) for snapshot in budgets]

    if projected_context > context_window_tokens:
        return PreflightAssessment(
            decision=RuntimeDecision.BLOCK,
            mode=RuntimePolicyMode.ENFORCE,
            reason="Projected request exceeds the model context window",
            projected_context_tokens=projected_context,
            context_remaining_tokens=remaining,
            context_utilization=utilization,
            budgets=projections,
        )

    enforced = next(
        (
            projection
            for projection in projections
            if projection.exceeded
            and projection.mode is RuntimePolicyMode.ENFORCE
        ),
        None,
    )
    if enforced is not None:
        return PreflightAssessment(
            decision=RuntimeDecision.BLOCK,
            mode=RuntimePolicyMode.ENFORCE,
            reason=f"Projected request exceeds budget '{enforced.name}'",
            projected_context_tokens=projected_context,
            context_remaining_tokens=remaining,
            context_utilization=utilization,
            budgets=projections,
            blocking_policy_id=enforced.policy_id,
        )

    warned = next(
        (
            projection
            for projection in projections
            if projection.exceeded and projection.mode is RuntimePolicyMode.WARN
        ),
        None,
    )
    if warned is not None:
        decision = RuntimeDecision.WARN
        reason = f"Projected request exceeds warning budget '{warned.name}'"
        mode = RuntimePolicyMode.WARN
    elif utilization >= warning_utilization:
        decision = RuntimeDecision.WARN
        reason = "Projected request is approaching the model context limit"
        mode = RuntimePolicyMode.WARN
    else:
        decision = RuntimeDecision.ALLOW
        reason = "Projected request fits the context window and active budgets"
        mode = RuntimePolicyMode.OBSERVE

    return PreflightAssessment(
        decision=decision,
        mode=mode,
        reason=reason,
        projected_context_tokens=projected_context,
        context_remaining_tokens=remaining,
        context_utilization=utilization,
        budgets=projections,
    )


def _project_budget(
    snapshot: BudgetSnapshot,
    request: RuntimePreflightRequest,
) -> RuntimeBudgetProjection:
    projected_requests = snapshot.consumed_requests + 1
    projected_tokens = (
        snapshot.consumed_tokens
        + request.input_tokens
        + request.requested_output_tokens
    )
    projected_cost = snapshot.consumed_cost + request.estimated_cost
    exceeded = any(
        (
            snapshot.max_requests is not None
            and projected_requests > snapshot.max_requests,
            snapshot.max_tokens is not None
            and projected_tokens > snapshot.max_tokens,
            snapshot.max_cost is not None
            and projected_cost > snapshot.max_cost,
        )
    )
    return RuntimeBudgetProjection(
        policy_id=snapshot.policy_id,
        name=snapshot.name,
        scope_type=snapshot.scope_type,
        period_type=snapshot.period_type,
        mode=snapshot.mode,
        consumed_requests=snapshot.consumed_requests,
        consumed_tokens=snapshot.consumed_tokens,
        consumed_cost=snapshot.consumed_cost,
        projected_requests=projected_requests,
        projected_tokens=projected_tokens,
        projected_cost=projected_cost,
        max_requests=snapshot.max_requests,
        max_tokens=snapshot.max_tokens,
        max_cost=snapshot.max_cost,
        exceeded=exceeded,
    )
