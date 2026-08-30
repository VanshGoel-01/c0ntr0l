from datetime import UTC, datetime
from uuid import UUID

import pytest
from app.domain.recovery import (
    RecoveryTrace,
    build_recovery_chat_request,
    estimate_chat_input_tokens,
)
from app.providers.registry import ProviderRegistry
from app.services.recovery import RecoveryRunner
from control_schemas import (
    ChatCompletion,
    ContinuityPacket,
    RecoveryStrategy,
    RuntimeCheckpoint,
    RuntimeRecoveryRequest,
    RuntimeRecoveryResult,
)

SOURCE_ID = UUID("00000000-0000-0000-0000-000000000010")
RESUMED_ID = UUID("00000000-0000-0000-0000-000000000011")
CHECKPOINT_ID = UUID("00000000-0000-0000-0000-000000000012")
TRACE = RecoveryTrace(
    execution_id=RESUMED_ID,
    root_span_id=UUID("00000000-0000-0000-0000-000000000013"),
    provider_span_id=UUID("00000000-0000-0000-0000-000000000014"),
    provider_attempt_id=UUID("00000000-0000-0000-0000-000000000015"),
)
COMPLETION = ChatCompletion.model_validate(
    {
        "id": "chatcmpl-recovered",
        "created": 0,
        "model": "mock-model",
        "choices": [
            {
                "message": {"role": "assistant", "content": "Task continued"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 2, "total_tokens": 22},
    }
)


def checkpoint() -> RuntimeCheckpoint:
    packet = ContinuityPacket(
        task="Research watershed monitoring",
        source_execution_id=SOURCE_ID,
        source_provider="mock",
        source_model="mock-model",
        completed_work=["Collected two sources"],
        failed_operation={"name": "search", "arguments": {"query": "watershed"}},
        reason_for_intervention="no_progress",
        recommended_action="Broaden the search query",
        evidence={"occurrence": 4},
        created_at=datetime.now(UTC),
    )
    return RuntimeCheckpoint(
        id=CHECKPOINT_ID,
        execution_id=SOURCE_ID,
        status="consumed",
        content_fingerprint="a" * 64,
        packet=packet,
        created_at=datetime.now(UTC),
    )


def prepared_result(provider: str = "mock") -> RuntimeRecoveryResult:
    return RuntimeRecoveryResult(
        source_execution_id=SOURCE_ID,
        strategy=RecoveryStrategy.RETRY_MODIFIED,
        status="prepared",
        resumed_execution_id=RESUMED_ID,
        target_provider=provider,
        target_model="mock-model",
        checkpoint=checkpoint(),
        message="Recovery prepared",
    )


class FakeRecoveryRepository:
    def __init__(self) -> None:
        self.started: tuple[object, ...] | None = None
        self.completed: tuple[object, ...] | None = None
        self.failed: tuple[object, ...] | None = None
        self.blocked: tuple[object, ...] | None = None

    async def start(self, *args: object) -> RecoveryTrace:
        self.started = args
        return TRACE

    async def complete(self, *args: object) -> None:
        self.completed = args

    async def fail(self, *args: object, **kwargs: object) -> None:
        self.failed = (*args, kwargs)

    async def block(self, *args: object) -> None:
        self.blocked = args


class FakeProvider:
    def __init__(self) -> None:
        self.request = None
        self.closed = False

    async def complete(self, request, demo_scenario=None):  # type: ignore[no-untyped-def]
        self.request = request
        return COMPLETION

    async def close(self) -> None:
        self.closed = True

    async def context_window(self, model: str) -> int | None:
        return 8_192


@pytest.mark.asyncio
async def test_recovery_runner_calls_provider_and_persists_completion() -> None:
    repository = FakeRecoveryRepository()
    provider = FakeProvider()
    runner = RecoveryRunner(
        repository,  # type: ignore[arg-type]
        ProviderRegistry({"mock": provider}),
        max_tokens=256,
    )
    request = RuntimeRecoveryRequest(
        strategy=RecoveryStrategy.RETRY_MODIFIED,
        modified_arguments={"query": "broader watershed monitoring research"},
    )

    result = await runner.run(prepared_result(), request)

    assert result.status == "completed"
    assert result.completion == COMPLETION
    assert repository.started == (RESUMED_ID, "mock", "mock-model")
    assert repository.completed is not None
    assert repository.failed is None
    assert provider.request.model == "mock-model"
    assert "broader watershed" in provider.request.messages[1].content


@pytest.mark.asyncio
async def test_unconfigured_provider_is_recorded_as_failed() -> None:
    repository = FakeRecoveryRepository()
    runner = RecoveryRunner(
        repository,  # type: ignore[arg-type]
        ProviderRegistry({}),
        max_tokens=256,
    )
    request = RuntimeRecoveryRequest(
        strategy=RecoveryStrategy.RETRY_MODIFIED,
        modified_arguments={"query": "broader query"},
    )

    result = await runner.run(prepared_result("paid-cloud"), request)

    assert result.status == "failed"
    assert "provider_not_configured" in result.message
    assert repository.failed is not None
    assert repository.completed is None


def test_recovery_prompt_redacts_sensitive_modified_arguments() -> None:
    request = build_recovery_chat_request(
        packet=checkpoint().packet,
        target_model="mock-model",
        modified_arguments={"query": "safe", "api_key": "must-not-leak"},
        max_tokens=128,
    )

    content = request.messages[1].content
    system_prompt = request.messages[0].content
    assert "must-not-leak" not in content
    assert "[REDACTED]" in content
    assert "replacement worker" in system_prompt
    assert "concrete next action" in system_prompt
    assert request.temperature == 0


def test_recovery_input_estimate_is_conservative() -> None:
    request = build_recovery_chat_request(
        packet=checkpoint().packet,
        target_model="mock-model",
        modified_arguments={"query": "broader query"},
        max_tokens=128,
    )

    content_bytes = sum(
        len(message.content.encode("utf-8")) for message in request.messages
    )
    assert estimate_chat_input_tokens(request) > content_bytes


@pytest.mark.asyncio
async def test_recovery_runner_records_preflight_block() -> None:
    repository = FakeRecoveryRepository()
    runner = RecoveryRunner(
        repository,  # type: ignore[arg-type]
        ProviderRegistry({}),
        max_tokens=128,
    )

    result = await runner.block(prepared_result(), "Budget exhausted")

    assert result.status == "blocked"
    assert repository.blocked == (RESUMED_ID, "Budget exhausted")
