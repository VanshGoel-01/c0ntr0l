import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_normal_completion_is_deterministic(
    client: AsyncClient,
    chat_payload: dict[str, object],
) -> None:
    first = await client.post("/v1/chat/completions", json=chat_payload)
    second = await client.post("/v1/chat/completions", json=chat_payload)

    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json()["choices"][0]["finish_reason"] == "stop"
    assert first.json()["usage"]["total_tokens"] > 0
    assert first.headers["x-mock-scenario"] == "normal"


@pytest.mark.asyncio
async def test_stream_uses_openai_sse_termination(
    client: AsyncClient,
    chat_payload: dict[str, object],
) -> None:
    chat_payload["stream"] = True
    response = await client.post("/v1/chat/completions", json=chat_payload)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "chat.completion.chunk" in response.text
    assert response.text.endswith("data: [DONE]\n\n")


@pytest.mark.asyncio
async def test_provider_error_is_explicit_and_sanitized(
    client: AsyncClient,
    chat_payload: dict[str, object],
) -> None:
    response = await client.post(
        "/v1/chat/completions",
        json=chat_payload,
        headers={"X-Mock-Scenario": "provider_error"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "mock_provider_unavailable"
    assert "Demonstrate c0ntr0l" not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_timeout_scenario_finishes_with_gateway_timeout(
    client: AsyncClient,
    chat_payload: dict[str, object],
) -> None:
    response = await client.post(
        "/v1/chat/completions",
        json=chat_payload,
        headers={"X-Mock-Scenario": "timeout"},
    )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "mock_provider_timeout"


@pytest.mark.asyncio
async def test_repeated_tool_scenario_has_a_stable_fingerprint_source(
    client: AsyncClient,
    chat_payload: dict[str, object],
) -> None:
    response = await client.post(
        "/v1/chat/completions",
        json=chat_payload,
        headers={"X-Mock-Scenario": "repeated_tool"},
    )

    message = response.json()["choices"][0]["message"]
    assert response.status_code == 200
    assert response.json()["choices"][0]["finish_reason"] == "tool_calls"
    assert message["tool_calls"][0]["function"] == {
        "name": "lookup_status",
        "arguments": '{"resource":"demo"}',
    }


@pytest.mark.asyncio
async def test_invalid_scenario_is_rejected(
    client: AsyncClient, chat_payload: dict[str, object]
) -> None:
    response = await client.post(
        "/v1/chat/completions",
        json=chat_payload,
        headers={"X-Mock-Scenario": "unknown"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_mock_scenario"


@pytest.mark.asyncio
async def test_oversized_message_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "mock-gpt",
            "messages": [{"role": "user", "content": "x" * 32_769}],
        },
    )

    assert response.status_code == 422
