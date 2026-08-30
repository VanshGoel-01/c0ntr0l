from uuid import UUID

import pytest
from app.domain.auth import ApiKeyPrincipal
from app.domain.preflight import PreflightExecution
from app.services.runtime import RuntimeService
from control_schemas import (
    ChatRequest,
    RecoveryStrategy,
    RuntimeDecision,
    RuntimePreflightResult,
    RuntimeRecoveryRequest,
)
from test_recovery_runner import prepared_result

PRINCIPAL = ApiKeyPrincipal(
    api_key_id=UUID("00000000-0000-0000-0000-000000000001"),
    organization_id=UUID("00000000-0000-0000-0000-000000000002"),
    project_id=UUID("00000000-0000-0000-0000-000000000003"),
)


class FakeRuntimeRepository:
    def __init__(self, result, decision=RuntimeDecision.ALLOW):  # type: ignore[no-untyped-def]
        self.result = result
        self.decision = decision
        self.preflight_request = None

    async def recover(self, principal, execution_id, request):  # type: ignore[no-untyped-def]
        return self.result.model_copy(update={"strategy": request.strategy})

    async def get_preflight_execution(self, principal, execution_id):  # type: ignore[no-untyped-def]
        return PreflightExecution(
            execution_id=execution_id,
            provider=self.result.target_provider,
            model=self.result.target_model,
        )

    async def record_preflight(self, principal, execution, request, **kwargs):  # type: ignore[no-untyped-def]
        self.preflight_request = request
        return RuntimePreflightResult(
            execution_id=execution.execution_id,
            decision=self.decision,
            reason=(
                "Budget exhausted"
                if self.decision is RuntimeDecision.BLOCK
                else "Within budget"
            ),
            provider=execution.provider,
            model=execution.model,
            input_tokens=request.input_tokens,
            reserved_output_tokens=request.requested_output_tokens,
            safety_margin_tokens=kwargs["safety_margin_tokens"],
            projected_context_tokens=512,
            context_window_tokens=8_192,
            context_remaining_tokens=7_680,
            context_utilization=0.0625,
        )


class FakeSignals:
    def __init__(self) -> None:
        self.cleared = []

    async def clear_cancellation(self, project_id, execution_id):  # type: ignore[no-untyped-def]
        self.cleared.append((project_id, execution_id))


class FakeRunner:
    def __init__(self) -> None:
        self.calls = []
        self.blocks = []

    def build_request(self, result, request):  # type: ignore[no-untyped-def]
        return ChatRequest(
            model=result.target_model,
            messages=[{"role": "user", "content": "Continue from checkpoint"}],
            max_tokens=128,
        )

    async def run(self, result, request, chat_request):  # type: ignore[no-untyped-def]
        self.calls.append((result, request, chat_request))
        return result.model_copy(update={"status": "completed"})

    async def block(self, result, reason):  # type: ignore[no-untyped-def]
        self.blocks.append((result, reason))
        return result.model_copy(update={"status": "blocked"})


class FakeProviders:
    async def context_window(self, provider, model, fallback):  # type: ignore[no-untyped-def]
        return fallback


@pytest.mark.asyncio
async def test_automatic_recovery_runs_provider_after_preparation() -> None:
    prepared = prepared_result()
    repository = FakeRuntimeRepository(prepared)
    signals = FakeSignals()
    runner = FakeRunner()
    service = RuntimeService(
        repository,  # type: ignore[arg-type]
        signals,  # type: ignore[arg-type]
        runner,  # type: ignore[arg-type]
        FakeProviders(),  # type: ignore[arg-type]
        8_192,
        256,
        0.85,
    )
    request = RuntimeRecoveryRequest(
        strategy=RecoveryStrategy.RETRY_MODIFIED,
        modified_arguments={"query": "broader query"},
    )

    result = await service.recover(PRINCIPAL, prepared.source_execution_id, request)

    assert result.status == "completed"
    assert len(runner.calls) == 1
    assert runner.blocks == []
    assert repository.preflight_request.requested_output_tokens == 128
    assert signals.cleared == [(PRINCIPAL.project_id, prepared.resumed_execution_id)]


@pytest.mark.asyncio
async def test_automatic_recovery_does_not_call_provider_when_preflight_blocks() -> (
    None
):
    prepared = prepared_result()
    repository = FakeRuntimeRepository(prepared, RuntimeDecision.BLOCK)
    runner = FakeRunner()
    service = RuntimeService(
        repository,  # type: ignore[arg-type]
        FakeSignals(),  # type: ignore[arg-type]
        runner,  # type: ignore[arg-type]
        FakeProviders(),  # type: ignore[arg-type]
        8_192,
        256,
        0.85,
    )
    request = RuntimeRecoveryRequest(
        strategy=RecoveryStrategy.RETRY_MODIFIED,
        modified_arguments={"query": "broader query"},
    )

    result = await service.recover(PRINCIPAL, prepared.source_execution_id, request)

    assert result.status == "blocked"
    assert runner.calls == []
    assert len(runner.blocks) == 1
    assert repository.preflight_request.requested_output_tokens == 128


@pytest.mark.asyncio
async def test_manual_resume_does_not_call_provider() -> None:
    prepared = prepared_result().model_copy(
        update={"strategy": RecoveryStrategy.MANUAL_RESUME}
    )
    runner = FakeRunner()
    service = RuntimeService(
        FakeRuntimeRepository(prepared),  # type: ignore[arg-type]
        FakeSignals(),  # type: ignore[arg-type]
        runner,  # type: ignore[arg-type]
        FakeProviders(),  # type: ignore[arg-type]
        8_192,
        256,
        0.85,
    )
    request = RuntimeRecoveryRequest(strategy=RecoveryStrategy.MANUAL_RESUME)

    result = await service.recover(PRINCIPAL, prepared.source_execution_id, request)

    assert result.status == "prepared"
    assert runner.calls == []
