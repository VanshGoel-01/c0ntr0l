import pytest
from app.providers.ollama import OllamaProviderClient
from httpx import MockTransport, Request, Response


@pytest.mark.asyncio
async def test_ollama_context_window_is_read_from_model_metadata() -> None:
    def handler(request: Request) -> Response:
        if request.url.path == "/api/ps":
            return Response(200, json={"models": []})
        assert request.url.path == "/api/show"
        return Response(
            200,
            json={"model_info": {"gemma3.context_length": 131_072}},
        )

    client = OllamaProviderClient(
        "http://ollama.test", 1, MockTransport(handler)
    )
    try:
        context_window = await client.context_window("gemma3:1b")
    finally:
        await client.close()

    assert context_window == 131_072


@pytest.mark.asyncio
async def test_ollama_prefers_active_runtime_context() -> None:
    def handler(request: Request) -> Response:
        assert request.url.path == "/api/ps"
        return Response(
            200,
            json={
                "models": [
                    {"name": "gemma3:1b", "context_length": 4_096}
                ]
            },
        )

    client = OllamaProviderClient(
        "http://ollama.test", 1, MockTransport(handler)
    )
    try:
        context_window = await client.context_window("gemma3:1b")
    finally:
        await client.close()

    assert context_window == 4_096
