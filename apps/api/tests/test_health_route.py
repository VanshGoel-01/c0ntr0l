import pytest
from app.api.router import api_router
from control_schemas import HealthResponse, HealthStatus
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


class FakeHealthService:
    def __init__(self, status: HealthStatus) -> None:
        self._status = status

    async def check(self) -> HealthResponse:
        return HealthResponse(status=self._status, version="test")


def create_test_app(status: HealthStatus) -> FastAPI:
    application = FastAPI()
    application.state.health_service = FakeHealthService(status)
    application.include_router(api_router)
    return application


@pytest.mark.asyncio
async def test_health_route_returns_the_shared_contract() -> None:
    transport = ASGITransport(app=create_test_app(HealthStatus.OK))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "c0ntr0l-api",
        "version": "test",
        "dependencies": {},
    }


@pytest.mark.asyncio
async def test_health_route_exposes_degraded_state() -> None:
    transport = ASGITransport(app=create_test_app(HealthStatus.DEGRADED))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
