from decimal import Decimal
from uuid import UUID

from app.domain.preflight import (
    BudgetSnapshot,
    ModelPolicySnapshot,
    evaluate_preflight,
)
from control_schemas import (
    ModelPolicyMode,
    RuntimeDecision,
    RuntimePolicyMode,
    RuntimePreflightRequest,
)

POLICY_ID = UUID("00000000-0000-0000-0000-000000000020")
MODEL_POLICY_ID = UUID("00000000-0000-0000-0000-000000000021")


def budget(
    *,
    mode: RuntimePolicyMode,
    consumed_tokens: int,
    max_tokens: int,
) -> BudgetSnapshot:
    return BudgetSnapshot(
        policy_id=POLICY_ID,
        name="Token limit",
        scope_type="project",
        period_type="daily",
        mode=mode,
        consumed_requests=3,
        consumed_tokens=consumed_tokens,
        consumed_cost=Decimal(0),
        max_requests=None,
        max_tokens=max_tokens,
        max_cost=None,
    )


def assess(
    request: RuntimePreflightRequest,
    budgets: list[BudgetSnapshot] | None = None,
    model_policy: ModelPolicySnapshot | None = None,
):  # type: ignore[no-untyped-def]
    return evaluate_preflight(
        request,
        budgets or [],
        model_policy=model_policy,
        context_window_tokens=8_192,
        safety_margin_tokens=256,
        warning_utilization=0.85,
    )


def test_context_overflow_blocks_before_model_call() -> None:
    result = assess(
        RuntimePreflightRequest(input_tokens=8_000, requested_output_tokens=512)
    )

    assert result.decision is RuntimeDecision.BLOCK
    assert result.context_remaining_tokens == 0
    assert "context window" in result.reason


def test_context_warning_reserves_requested_output() -> None:
    result = assess(
        RuntimePreflightRequest(input_tokens=6_500, requested_output_tokens=512)
    )

    assert result.decision is RuntimeDecision.WARN
    assert result.projected_context_tokens == 7_268


def test_enforced_budget_blocks_projected_usage() -> None:
    result = assess(
        RuntimePreflightRequest(input_tokens=300, requested_output_tokens=300),
        [
            budget(
                mode=RuntimePolicyMode.ENFORCE,
                consumed_tokens=9_600,
                max_tokens=10_000,
            )
        ],
    )

    assert result.decision is RuntimeDecision.BLOCK
    assert result.blocking_policy_id == POLICY_ID
    assert result.budgets[0].projected_tokens == 10_200


def test_observe_budget_reports_excess_without_blocking() -> None:
    result = assess(
        RuntimePreflightRequest(input_tokens=300, requested_output_tokens=300),
        [
            budget(
                mode=RuntimePolicyMode.OBSERVE,
                consumed_tokens=9_600,
                max_tokens=10_000,
            )
        ],
    )

    assert result.decision is RuntimeDecision.ALLOW
    assert result.budgets[0].exceeded is True


def model_policy(
    mode: ModelPolicyMode,
    token_limit: int | None,
) -> ModelPolicySnapshot:
    return ModelPolicySnapshot(
        policy_id=MODEL_POLICY_ID,
        provider="ollama",
        model="qwen2.5:0.5b",
        mode=mode,
        token_limit=token_limit,
    )


def test_block_mode_without_limit_disables_model() -> None:
    result = assess(
        RuntimePreflightRequest(input_tokens=200, requested_output_tokens=200),
        model_policy=model_policy(ModelPolicyMode.BLOCK, None),
    )

    assert result.decision is RuntimeDecision.BLOCK
    assert result.blocking_model_policy_id == MODEL_POLICY_ID
    assert result.model_policy is not None
    assert result.model_policy.triggered is True


def test_block_mode_enforces_per_call_token_limit() -> None:
    allowed = assess(
        RuntimePreflightRequest(input_tokens=200, requested_output_tokens=200),
        model_policy=model_policy(ModelPolicyMode.BLOCK, 500),
    )
    blocked = assess(
        RuntimePreflightRequest(input_tokens=300, requested_output_tokens=300),
        model_policy=model_policy(ModelPolicyMode.BLOCK, 500),
    )

    assert allowed.decision is RuntimeDecision.ALLOW
    assert blocked.decision is RuntimeDecision.BLOCK
    assert blocked.model_policy is not None
    assert blocked.model_policy.projected_tokens == 600


def test_warn_mode_reports_policy_trigger_without_blocking() -> None:
    result = assess(
        RuntimePreflightRequest(input_tokens=300, requested_output_tokens=300),
        model_policy=model_policy(ModelPolicyMode.WARN, 500),
    )

    assert result.decision is RuntimeDecision.WARN
    assert "model warning limit" in result.reason
