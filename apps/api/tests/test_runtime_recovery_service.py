from uuid import UUID

import pytest
from app.domain.auth import ApiKeyPrincipal
from app.services.runtime import RuntimeService
from control_schemas import RecoveryStrategy, RuntimeRecoveryRequest

from test_recovery_runner import prepared_result

PRINCIPAL = ApiKeyPrincipal(
    api_key_id=UUID("00000000-0000-0000-0000-000000000001"),
    organization_id=UUID("00000000-0000-0000-0000-000000000002"),
    project_id=UUID("00000000-0000-0000-0000-000000000003"),
)


class FakeRuntimeRepository:
    def __init__(self, result):  # type: ignore[no-untyped-def]
        self.result = result

    async def recover(self, principal, execution_id, request):  # type: ignore[no-untyped-def]
        return self.result.model_copy(update={"strategy": request.strategy})


class FakeSignals:
    def __init__(self) -> None:
        self.cleared = []

    async def clear_cancellation(self, execution_id):  # type: ignore[no-untyped-def]
        self.cleared.append(execution_id)


class FakeRunner:
    def __init__(self) -> None:
        self.calls = []

    async def run(self, result, request):  # type: ignore[no-untyped-def]
        self.calls.append((result, request))
        return result.model_copy(update={"status": "completed"})


class FakeProviders:
    async def context_window(self, provider, model, fallback):  # type: ignore[no-untyped-def]
        return fallback


@pytest.mark.asyncio
async def test_automatic_recovery_runs_provider_after_preparation() -> None:
    prepared = prepared_result()
    signals = FakeSignals()
    runner = FakeRunner()
    service = RuntimeService(
        FakeRuntimeRepository(prepared),  # type: ignore[arg-type]
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
    assert signals.cleared == [prepared.resumed_execution_id]


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
