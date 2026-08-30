from datetime import UTC, datetime
from uuid import UUID

import pytest
from app.api.dependencies import get_principal, get_provider_registry
from app.api.routes.providers import router
from app.domain.auth import ApiKeyPrincipal
from control_schemas import (
    ProviderAvailability,
    ProviderCatalog,
    ProviderSummary,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

PRINCIPAL = ApiKeyPrincipal(
    api_key_id=UUID("00000000-0000-0000-0000-000000000001"),
    organization_id=UUID("00000000-0000-0000-0000-000000000002"),
    project_id=UUID("00000000-0000-0000-0000-000000000003"),
)


class FakeRegistry:
    async def catalog(self) -> ProviderCatalog:
        return ProviderCatalog(
            checked_at=datetime.now(UTC),
            providers=[
                ProviderSummary(
                    name="ollama",
                    status=ProviderAvailability.OPERATIONAL,
                    models=["qwen2.5:0.5b"],
                )
            ],
        )


@pytest.mark.asyncio
async def test_provider_catalog_returns_only_registry_models() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_provider_registry] = lambda: FakeRegistry()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/providers")

    assert response.status_code == 200
    assert response.json()["providers"] == [
        {
            "name": "ollama",
            "status": "operational",
            "models": ["qwen2.5:0.5b"],
        }
    ]
