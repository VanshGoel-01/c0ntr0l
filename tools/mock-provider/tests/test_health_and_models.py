import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_reports_service_identity(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "c0ntr0l-mock-provider",
        "version": "0.1.0",
    }


@pytest.mark.asyncio
async def test_models_lists_the_free_demo_model(client: AsyncClient) -> None:
    response = await client.get("/v1/models")

    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "mock-gpt"
