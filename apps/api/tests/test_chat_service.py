from datetime import UTC, datetime
from uuid import UUID

import pytest
from app.domain.auth import ApiKeyPrincipal
from app.domain.executions import ExecutionTrace
from app.providers.errors import ProviderUnavailableError
from app.providers.registry import ProviderRegistry
from app.services.chat import ChatPolicyBlockedError, ChatService
from control_schemas import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatRequest,
    ModelPolicyContext,
    ModelPolicyMode,
    RuntimeDecision,
)

PRINCIPAL = ApiKeyPrincipal(
    api_key_id=UUID("00000000-0000-0000-0000-000000000001"),
    organization_id=UUID("00000000-0000-0000-0000-000000000002"),
    project_id=UUID("00000000-0000-0000-0000-000000000003"),
)
TRACE = ExecutionTrace(
    execution_id=UUID("00000000-0000-0000-0000-000000000010"),
    root_span_id=UUID("00000000-0000-0000-0000-000000000011"),
    provider_span_id=UUID("00000000-0000-0000-0000-000000000012"),
    provider_attempt_id=UUID("00000000-0000-0000-0000-000000000013"),
    provider_name="mock",
)
CHECKPOINT_ID = UUID("00000000-0000-0000-0000-000000000014")
REQUEST = ChatRequest(
    model="mock-gpt",
    messages=[{"role": "user", "content": "private prompt"}],
)
COMPLETION = ChatCompletion.model_validate(
    {
        "id": "chatcmpl-test",
        "created": 0,
        "model": "mock-gpt",
        "choices": [
            {
                "message": {"role": "assistant", "content": "private output"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
    }
)


class FakeExecutionRepository:
    def __init__(self) -> None:
        self.started: tuple[object, ...] | None = None
        self.completed: tuple[object, ...] | None = None
        self.failed: tuple[object, ...] | None = None
        self.policy_assessment = None

    async def start(self, *args: object) -> ExecutionTrace:
        self.started = args
        return TRACE

    async def complete(self, *args: object) -> None:
        self.completed = args

    async def fail(self, *args: object, **kwargs: object) -> None:
        self.failed = (*args, kwargs)

    async def record_model_policy(self, trace, model, assessment):  # type: ignore[no-untyped-def]
        self.policy_assessment = assessment
        return CHECKPOINT_ID if assessment.decision is RuntimeDecision.BLOCK else None


class FakeProvider:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.complete_calls = 0
        self.stream_calls = 0

    async def complete(
        self,
        request: ChatRequest,
        scenario: str | None,
    ) -> ChatCompletion:
        self.complete_calls += 1
        if self.error is not None:
            raise self.error
        return COMPLETION

    async def list_models(self) -> tuple[str, ...]:
        return ("mock-gpt",)

    async def stream(self, request, scenario=None):  # type: ignore[no-untyped-def]
        self.stream_calls += 1
        if self.error is not None:
            raise self.error
        for chunk in stream_chunks():
            yield chunk


class FakeModelPolicyRepository:
    def __init__(self, mode: ModelPolicyMode, token_limit: int | None = None) -> None:
        now = datetime.now(UTC)
        self.context = ModelPolicyContext(
            id=UUID("00000000-0000-0000-0000-000000000020"),
            project_id=PRINCIPAL.project_id,
            provider="mock",
            model="mock-gpt",
            mode=mode,
            token_limit=token_limit,
            created_at=now,
            updated_at=now,
        )

    async def get(self, project_id, provider, model):  # type: ignore[no-untyped-def]
        assert project_id == PRINCIPAL.project_id
        assert provider == "mock"
        assert model == "mock-gpt"
        return self.context


def stream_chunks() -> list[ChatCompletionChunk]:
    common = {
        "id": COMPLETION.id,
        "created": COMPLETION.created,
        "model": COMPLETION.model,
    }
    return [
        ChatCompletionChunk.model_validate(
            {
                **common,
                "choices": [
                    {
                        "delta": {"role": "assistant", "content": "private"},
                        "finish_reason": None,
                    }
                ],
            }
        ),
        ChatCompletionChunk.model_validate(
            {
                **common,
                "choices": [
                    {
                        "delta": {"content": " output"},
                        "finish_reason": None,
                    }
                ],
            }
        ),
        ChatCompletionChunk.model_validate(
            {
                **common,
                "choices": [{"delta": {}, "finish_reason": "stop"}],
                "usage": COMPLETION.usage.model_dump(),
            }
        ),
    ]


@pytest.mark.asyncio
async def test_chat_service_records_trace_usage_and_only_fingerprints_content() -> None:
    repository = FakeExecutionRepository()
    service = ChatService(
        repository,
        ProviderRegistry({"mock": FakeProvider()}),  # type: ignore[arg-type]
    )

    result = await service.complete(PRINCIPAL, REQUEST, "request-1", None)

    assert result.execution_id == str(TRACE.execution_id)
    assert result.decision is RuntimeDecision.ALLOW
    assert result.completion == COMPLETION
    assert repository.started is not None
    assert repository.completed is not None
    assert repository.started[2] == "mock"
    input_fingerprint = repository.started[5]
    output_fingerprint = repository.completed[3]
    assert len(str(input_fingerprint)) == 64
    assert len(str(output_fingerprint)) == 64
    assert "private prompt" not in str(repository.started)
    assert "private output" not in str(repository.completed[3:])


@pytest.mark.asyncio
async def test_provider_failure_is_written_to_the_execution_trace() -> None:
    repository = FakeExecutionRepository()
    service = ChatService(  # type: ignore[arg-type]
        repository,
        ProviderRegistry(
            {"mock": FakeProvider(ProviderUnavailableError())}  # type: ignore[arg-type]
        ),
    )

    with pytest.raises(ProviderUnavailableError):
        await service.complete(PRINCIPAL, REQUEST, "request-2", None)

    assert repository.failed is not None
    assert repository.completed is None
    assert "provider_unavailable" in str(repository.failed)


@pytest.mark.asyncio
async def test_streaming_relays_chunks_and_reconciles_after_done() -> None:
    repository = FakeExecutionRepository()
    service = ChatService(
        repository,
        ProviderRegistry({"mock": FakeProvider()}),  # type: ignore[arg-type]
    )
    streaming_request = REQUEST.model_copy(update={"stream": True})

    result = await service.stream(PRINCIPAL, streaming_request, None, None)
    events = [event async for event in result.events]

    assert result.execution_id == str(TRACE.execution_id)
    assert events[-1] == "data: [DONE]\n\n"
    assert repository.started is not None
    assert repository.started[3] is True
    assert repository.completed is not None
    assert repository.failed is None
    assert result.decision is RuntimeDecision.ALLOW
    assert "private output" not in str(repository.completed[3:])


@pytest.mark.asyncio
async def test_streaming_provider_failure_is_recorded_before_response() -> None:
    repository = FakeExecutionRepository()
    service = ChatService(  # type: ignore[arg-type]
        repository,
        ProviderRegistry(
            {"mock": FakeProvider(ProviderUnavailableError())}  # type: ignore[arg-type]
        ),
    )

    with pytest.raises(ProviderUnavailableError):
        await service.stream(
            PRINCIPAL,
            REQUEST.model_copy(update={"stream": True}),
            None,
            None,
        )

    assert repository.failed is not None
    assert repository.completed is None


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_block_policy_prevents_provider_invocation(stream: bool) -> None:
    repository = FakeExecutionRepository()
    provider = FakeProvider()
    service = ChatService(
        repository,  # type: ignore[arg-type]
        ProviderRegistry({"mock": provider}),  # type: ignore[arg-type]
        model_policies=FakeModelPolicyRepository(ModelPolicyMode.BLOCK),  # type: ignore[arg-type]
    )
    request = REQUEST.model_copy(update={"stream": stream})

    with pytest.raises(ChatPolicyBlockedError) as raised:
        if stream:
            await service.stream(PRINCIPAL, request, None, None)
        else:
            await service.complete(PRINCIPAL, request, None, None)

    assert raised.value.execution_id == TRACE.execution_id
    assert raised.value.checkpoint_id == CHECKPOINT_ID
    assert provider.complete_calls == 0
    assert provider.stream_calls == 0
    assert repository.completed is None
    assert repository.failed is None
    assert repository.policy_assessment.decision is RuntimeDecision.BLOCK


@pytest.mark.asyncio
async def test_warn_policy_records_decision_and_allows_provider_call() -> None:
    repository = FakeExecutionRepository()
    provider = FakeProvider()
    service = ChatService(
        repository,  # type: ignore[arg-type]
        ProviderRegistry({"mock": provider}),  # type: ignore[arg-type]
        model_policies=FakeModelPolicyRepository(ModelPolicyMode.WARN),  # type: ignore[arg-type]
    )

    result = await service.complete(PRINCIPAL, REQUEST, None, None)

    assert result.decision is RuntimeDecision.WARN
    assert provider.complete_calls == 1
    assert repository.completed is not None
    assert repository.policy_assessment.decision is RuntimeDecision.WARN


@pytest.mark.asyncio
async def test_admission_failure_marks_trace_failed_without_calling_provider() -> None:
    class BrokenModelPolicyRepository:
        async def get(self, *args):  # type: ignore[no-untyped-def]
            raise RuntimeError("policy store unavailable")

    repository = FakeExecutionRepository()
    provider = FakeProvider()
    service = ChatService(
        repository,  # type: ignore[arg-type]
        ProviderRegistry({"mock": provider}),  # type: ignore[arg-type]
        model_policies=BrokenModelPolicyRepository(),  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="policy store unavailable"):
        await service.complete(PRINCIPAL, REQUEST, None, None)

    assert provider.complete_calls == 0
    assert repository.completed is None
    assert repository.failed is not None
    assert "admission_control_error" in str(repository.failed)
