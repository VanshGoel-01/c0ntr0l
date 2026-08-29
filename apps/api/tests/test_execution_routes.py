from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from app.api.dependencies import get_execution_query_service, get_principal
from app.api.routes.executions import router
from app.domain.auth import ApiKeyPrincipal
from control_schemas import ExecutionDetail, ExecutionSummary
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

EXECUTION_ID = UUID("00000000-0000-0000-0000-000000000010")
PRINCIPAL = ApiKeyPrincipal(
    api_key_id=UUID("00000000-0000-0000-0000-000000000001"),
    organization_id=UUID("00000000-0000-0000-0000-000000000002"),
    project_id=UUID("00000000-0000-0000-0000-000000000003"),
)
SUMMARY = ExecutionSummary(
    id=EXECUTION_ID,
    status="completed",
    requested_model="mock-gpt",
    active_provider="mock",
    active_model="mock-gpt",
    is_streaming=False,
    input_fingerprint="a" * 64,
    output_fingerprint="b" * 64,
    final_reason="stop",
    error_code=None,
    started_at=datetime(2026, 8, 29, tzinfo=UTC),
    completed_at=datetime(2026, 8, 29, 0, 0, 1, tzinfo=UTC),
    duration_ms=1000,
    span_count=2,
    total_tokens=10,
    total_cost=Decimal(0),
)


class FakeExecutionQueryService:
    def __init__(self, detail: ExecutionDetail | None = None) -> None:
        self.detail = detail
        self.principal: ApiKeyPrincipal | None = None

    async def list_recent(
        self,
        principal: ApiKeyPrincipal,
        limit: int,
    ) -> list[ExecutionSummary]:
        self.principal = principal
        return [SUMMARY]

    async def get(
        self,
        principal: ApiKeyPrincipal,
        execution_id: UUID,
    ) -> ExecutionDetail | None:
        self.principal = principal
        return self.detail if execution_id == EXECUTION_ID else None


def create_test_app(service: FakeExecutionQueryService) -> FastAPI:
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_principal] = lambda: PRINCIPAL
    application.dependency_overrides[get_execution_query_service] = lambda: service
    return application


@pytest.mark.asyncio
async def test_execution_list_is_scoped_to_authenticated_principal() -> None:
    service = FakeExecutionQueryService()
    transport = ASGITransport(app=create_test_app(service))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/executions?limit=5")

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(EXECUTION_ID)
    assert response.json()[0]["span_count"] == 2
    assert service.principal == PRINCIPAL


@pytest.mark.asyncio
async def test_execution_detail_returns_spans_and_usage() -> None:
    detail = ExecutionDetail(**SUMMARY.model_dump(), spans=[], usage=[])
    service = FakeExecutionQueryService(detail)
    transport = ASGITransport(app=create_test_app(service))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/executions/{EXECUTION_ID}")

    assert response.status_code == 200
    assert response.json()["spans"] == []
    assert response.json()["usage"] == []


@pytest.mark.asyncio
async def test_execution_from_another_project_is_hidden_as_not_found() -> None:
    service = FakeExecutionQueryService()
    transport = ASGITransport(app=create_test_app(service))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/executions/{EXECUTION_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Execution not found"
