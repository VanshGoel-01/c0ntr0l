from uuid import UUID

import pytest
from app.domain.auth import ApiKeyPrincipal
from app.domain.executions import ExecutionTrace
from app.providers.errors import ProviderUnavailableError
from app.services.chat import ChatService, StreamingNotImplementedError
from control_schemas import ChatCompletion, ChatRequest

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
)
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

    async def start(self, *args: object) -> ExecutionTrace:
        self.started = args
        return TRACE

    async def complete(self, *args: object) -> None:
        self.completed = args

    async def fail(self, *args: object, **kwargs: object) -> None:
        self.failed = (*args, kwargs)


class FakeProvider:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def complete(
        self,
        request: ChatRequest,
        scenario: str | None,
    ) -> ChatCompletion:
        if self.error is not None:
            raise self.error
        return COMPLETION


@pytest.mark.asyncio
async def test_chat_service_records_trace_usage_and_only_fingerprints_content() -> None:
    repository = FakeExecutionRepository()
    service = ChatService(repository, FakeProvider())  # type: ignore[arg-type]

    result = await service.complete(PRINCIPAL, REQUEST, "request-1", None)

    assert result.execution_id == str(TRACE.execution_id)
    assert result.completion == COMPLETION
    assert repository.started is not None
    assert repository.completed is not None
    input_fingerprint = repository.started[4]
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
        FakeProvider(ProviderUnavailableError()),
    )

    with pytest.raises(ProviderUnavailableError):
        await service.complete(PRINCIPAL, REQUEST, "request-2", None)

    assert repository.failed is not None
    assert repository.completed is None
    assert "provider_unavailable" in str(repository.failed)


@pytest.mark.asyncio
async def test_streaming_is_rejected_before_an_execution_is_created() -> None:
    repository = FakeExecutionRepository()
    service = ChatService(repository, FakeProvider())  # type: ignore[arg-type]
    streaming_request = REQUEST.model_copy(update={"stream": True})

    with pytest.raises(StreamingNotImplementedError):
        await service.complete(PRINCIPAL, streaming_request, None, None)

    assert repository.started is None
