from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from mock_provider.core.config import Settings
from mock_provider.main import create_app


@pytest.fixture
def app() -> FastAPI:
    return create_app(Settings(timeout_delay_seconds=0.01))


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://mock-provider.test",
    ) as test_client:
        yield test_client


@pytest.fixture
def chat_payload() -> dict[str, object]:
    return {
        "model": "mock-gpt",
        "messages": [{"role": "user", "content": "Demonstrate c0ntr0l."}],
        "stream": False,
        "max_tokens": 128,
    }
