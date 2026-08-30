import json

import pytest
from app.providers.errors import ProviderResponseError, ProviderTimeoutError
from app.providers.http import HttpProviderClient
from control_schemas import ChatRequest
from httpx import MockTransport, ReadTimeout, Request, Response

REQUEST = ChatRequest(
    model="mock-gpt",
    messages=[{"role": "user", "content": "Test provider transport"}],
)


def completion_payload() -> dict[str, object]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "mock-gpt",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "done"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
    }


@pytest.mark.asyncio
async def test_provider_client_normalizes_response_and_forwards_demo_scenario() -> None:
    def handler(request: Request) -> Response:
        assert request.headers["x-mock-scenario"] == "repeated_tool"
        assert "authorization" not in request.headers
        assert json.loads(request.content)["model"] == "mock-gpt"
        return Response(200, json=completion_payload())

    client = HttpProviderClient("http://provider.test", 1, MockTransport(handler))
    try:
        completion = await client.complete(REQUEST, "repeated_tool")
    finally:
        await client.close()

    assert completion.id == "chatcmpl-test"
    assert completion.usage.total_tokens == 4


@pytest.mark.asyncio
async def test_provider_client_rejects_untrusted_response_shape() -> None:
    client = HttpProviderClient(
        "http://provider.test",
        1,
        MockTransport(lambda request: Response(200, json={"unexpected": True})),
    )
    try:
        with pytest.raises(ProviderResponseError):
            await client.complete(REQUEST)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_provider_timeout_is_sanitized() -> None:
    def handler(request: Request) -> Response:
        raise ReadTimeout("secret provider detail", request=request)

    client = HttpProviderClient("http://provider.test", 1, MockTransport(handler))
    try:
        with pytest.raises(ProviderTimeoutError) as error:
            await client.complete(REQUEST)
    finally:
        await client.close()

    assert str(error.value) == ""


@pytest.mark.asyncio
async def test_provider_gateway_timeout_is_classified_as_timeout() -> None:
    client = HttpProviderClient(
        "http://provider.test",
        1,
        MockTransport(lambda request: Response(504, json={"error": "timeout"})),
    )
    try:
        with pytest.raises(ProviderTimeoutError):
            await client.complete(REQUEST)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_provider_stream_validates_and_returns_typed_chunks() -> None:
    event = {
        "id": "chatcmpl-stream",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "mock-gpt",
        "choices": [
            {"index": 0, "delta": {"content": "done"}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
    }

    def handler(request: Request) -> Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert payload["stream_options"] == {"include_usage": True}
        body = f"data: {json.dumps(event)}\n\ndata: [DONE]\n\n"
        return Response(200, text=body, headers={"content-type": "text/event-stream"})

    client = HttpProviderClient("http://provider.test", 1, MockTransport(handler))
    try:
        chunks = [chunk async for chunk in client.stream(REQUEST)]
    finally:
        await client.close()

    assert len(chunks) == 1
    assert chunks[0].usage.total_tokens == 4
