from datetime import UTC, datetime
from uuid import UUID

import pytest
from app.api.dependencies import get_incident_service, get_principal
from app.api.routes.incidents import router
from app.domain.auth import ApiKeyPrincipal
from app.repositories.incidents import IncidentNotFoundError
from control_schemas import IncidentContext, IncidentStatus
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

PRINCIPAL = ApiKeyPrincipal(
    api_key_id=UUID("00000000-0000-0000-0000-000000000001"),
    organization_id=UUID("00000000-0000-0000-0000-000000000002"),
    project_id=UUID("00000000-0000-0000-0000-000000000003"),
)
INCIDENT_ID = UUID("00000000-0000-0000-0000-000000000010")
EXECUTION_ID = UUID("00000000-0000-0000-0000-000000000011")


def incident(status: IncidentStatus = IncidentStatus.OPEN) -> IncidentContext:
    return IncidentContext(
        id=INCIDENT_ID,
        execution_id=EXECUTION_ID,
        trace_id="trace_test",
        application_name="Research Agent",
        provider="ollama",
        model="qwen2.5:0.5b",
        incident_type="runaway_loop",
        severity="critical",
        status=status,
        title="Runaway loop blocked",
        evidence={"repeat_count": 4},
        created_at=datetime.now(UTC),
        acknowledged_at=None,
        resolved_at=None,
    )


class FakeIncidentService:
    async def list(self, principal, *, limit, status):  # type: ignore[no-untyped-def]
        assert principal == PRINCIPAL
        assert limit == 25
        assert status is IncidentStatus.OPEN
        return [incident()]

    async def update_status(self, principal, incident_id, status):  # type: ignore[no-untyped-def]
        assert principal == PRINCIPAL
        if incident_id != INCIDENT_ID:
            raise IncidentNotFoundError
        return incident(status)


def build_app() -> FastAPI:
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_principal] = lambda: PRINCIPAL
    application.dependency_overrides[get_incident_service] = FakeIncidentService
    return application


@pytest.mark.asyncio
async def test_list_incidents_is_project_scoped_and_filterable() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/incidents?limit=25&status=open")

    assert response.status_code == 200
    assert response.json()[0]["execution_id"] == str(EXECUTION_ID)


@pytest.mark.asyncio
async def test_update_incident_status_uses_typed_body() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()), base_url="http://test"
    ) as client:
        response = await client.patch(
            f"/api/v1/incidents/{INCIDENT_ID}",
            json={"status": "resolved"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "resolved"


@pytest.mark.asyncio
async def test_update_incident_status_hides_other_projects() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()), base_url="http://test"
    ) as client:
        response = await client.patch(
            "/api/v1/incidents/00000000-0000-0000-0000-000000000099",
            json={"status": "acknowledged"},
        )

    assert response.status_code == 404
