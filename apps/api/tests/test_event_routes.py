from datetime import UTC, datetime
from uuid import UUID

import pytest
from app.api.dependencies import get_execution_events, get_principal
from app.api.routes.events import router
from app.domain.auth import ApiKeyPrincipal
from control_schemas import ControlEvent, ControlEventType
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000003")
EXECUTION_ID = UUID("00000000-0000-0000-0000-000000000004")
PRINCIPAL = ApiKeyPrincipal(
    api_key_id=UUID("00000000-0000-0000-0000-000000000001"),
    organization_id=UUID("00000000-0000-0000-0000-000000000002"),
    project_id=PROJECT_ID,
)


class FakeEvents:
    def __init__(self) -> None:
        self.project_id = None
        self.last_event_id = None

    async def subscribe(self, project_id, last_event_id):  # type: ignore[no-untyped-def]
        self.project_id = project_id
        self.last_event_id = last_event_id
        yield ControlEvent(
            id="20-1",
            type=ControlEventType.EXECUTION_UPDATED,
            execution_id=EXECUTION_ID,
            occurred_at=datetime.now(UTC),
        )


def build_app(events: FakeEvents) -> FastAPI:
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_principal] = lambda: PRINCIPAL
    application.dependency_overrides[get_execution_events] = lambda: events
    return application


@pytest.mark.asyncio
async def test_event_stream_is_authenticated_and_project_scoped() -> None:
    events = FakeEvents()
    async with AsyncClient(
        transport=ASGITransport(app=build_app(events)), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/events",
            headers={"Last-Event-ID": "19-0"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "id: 20-1" in response.text
    assert '"execution_id":"00000000-0000-0000-0000-000000000004"' in response.text
    assert events.project_id == PROJECT_ID
    assert events.last_event_id == "19-0"


@pytest.mark.asyncio
async def test_event_stream_rejects_invalid_resume_cursor() -> None:
    events = FakeEvents()
    async with AsyncClient(
        transport=ASGITransport(app=build_app(events)), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/events",
            headers={"Last-Event-ID": "not-a-redis-id"},
        )

    assert response.status_code == 422
