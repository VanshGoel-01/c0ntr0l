from types import SimpleNamespace
from uuid import UUID

import pytest
from app.api.dependencies import get_chat_service, get_principal
from app.api.routes.chat import router
from app.domain.auth import ApiKeyPrincipal
from app.providers.errors import (
    ProviderModelNotFoundError,
    ProviderNotConfiguredError,
    ProviderScenarioUnsupportedError,
    ProviderSelectionAmbiguousError,
)
from app.services.chat import ChatPolicyBlockedError, ChatResult, ChatStreamResult
from control_schemas import ChatCompletion, RuntimeDecision
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

PRINCIPAL = ApiKeyPrincipal(
    api_key_id=UUID("00000000-0000-0000-0000-000000000001"),
    organization_id=UUID("00000000-0000-0000-0000-000000000002"),
    project_id=UUID("00000000-0000-0000-0000-000000000003"),
)
EXECUTION_ID = "00000000-0000-0000-0000-000000000004"
CHECKPOINT_ID = UUID("00000000-0000-0000-0000-000000000005")


class FakeChatService:
    def __init__(self, error: Exception | None = None) -> None:
        self.request = None
        self.kwargs = None
        self.error = error

    async def complete(self, principal, request, **kwargs):  # type: ignore[no-untyped-def]
        self.request = request
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return ChatResult(
            execution_id=EXECUTION_ID,
            provider_name="mock",
            decision=RuntimeDecision.WARN,
            completion=ChatCompletion.model_validate(
                {
                    "id": "chatcmpl-route",
                    "created": 0,
                    "model": request.model,
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "done"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                }
            ),
        )

    async def stream(self, principal, request, **kwargs):  # type: ignore[no-untyped-def]
        self.request = request
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error

        async def events():  # type: ignore[no-untyped-def]
            yield 'data: {"id":"chunk-1"}\n\n'
            yield "data: [DONE]\n\n"

        return ChatStreamResult(
            execution_id=EXECUTION_ID,
            provider_name="mock",
            decision=RuntimeDecision.ALLOW,
            events=events(),
        )


def build_app(service: FakeChatService) -> FastAPI:
    application = FastAPI()
    application.state.settings = SimpleNamespace(allow_demo_scenarios=True)
    application.include_router(router)
    application.dependency_overrides[get_principal] = lambda: PRINCIPAL
    application.dependency_overrides[get_chat_service] = lambda: service
    return application


@pytest.mark.asyncio
async def test_streaming_chat_returns_compatible_sse_and_execution_header() -> None:
    service = FakeChatService()
    async with AsyncClient(
        transport=ASGITransport(app=build_app(service)), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
            headers={"X-Control-Provider": "mock"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-control-execution-id"] == EXECUTION_ID
    assert response.headers["x-control-provider"] == "mock"
    assert response.headers["x-control-decision"] == "allow"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.text.endswith("data: [DONE]\n\n")
    assert service.request.stream is True
    assert service.kwargs["requested_provider"] == "mock"


@pytest.mark.asyncio
async def test_non_streaming_chat_reports_warn_decision_header() -> None:
    service = FakeChatService()
    async with AsyncClient(
        transport=ASGITransport(app=build_app(service)), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-gpt",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

    assert response.status_code == 200
    assert response.headers["x-control-execution-id"] == EXECUTION_ID
    assert response.headers["x-control-provider"] == "mock"
    assert response.headers["x-control-decision"] == "warn"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (ProviderModelNotFoundError(), 404),
        (ProviderSelectionAmbiguousError(), 409),
        (ProviderScenarioUnsupportedError(), 400),
        (ProviderNotConfiguredError(), 400),
    ],
)
@pytest.mark.asyncio
async def test_chat_route_maps_provider_selection_errors(
    error: Exception,
    expected_status: int,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app(FakeChatService(error))),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "unknown",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
        )

    assert response.status_code == expected_status


@pytest.mark.asyncio
async def test_blocked_chat_returns_checkpoint_and_trace_headers() -> None:
    error = ChatPolicyBlockedError(
        execution_id=UUID(EXECUTION_ID),
        provider_name="mock",
        reason="Model is blocked by the project policy",
        checkpoint_id=CHECKPOINT_ID,
    )
    async with AsyncClient(
        transport=ASGITransport(app=build_app(FakeChatService(error))),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-gpt",
                "messages": [{"role": "user", "content": "private prompt"}],
                "stream": True,
            },
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Model is blocked by the project policy"}
    assert response.headers["x-control-execution-id"] == EXECUTION_ID
    assert response.headers["x-control-provider"] == "mock"
    assert response.headers["x-control-decision"] == "block"
    assert response.headers["x-control-checkpoint-id"] == str(CHECKPOINT_ID)
    assert response.headers["cache-control"] == "no-store"
    assert "private prompt" not in response.text
