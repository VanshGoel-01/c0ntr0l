from datetime import UTC, datetime
from uuid import UUID

import pytest
from app.api.dependencies import get_model_policy_service, get_principal
from app.api.routes.model_policies import router
from app.domain.auth import ApiKeyPrincipal
from control_schemas import ModelPolicyContext
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

PRINCIPAL = ApiKeyPrincipal(
    api_key_id=UUID("00000000-0000-0000-0000-000000000001"),
    organization_id=UUID("00000000-0000-0000-0000-000000000002"),
    project_id=UUID("00000000-0000-0000-0000-000000000003"),
)
POLICY_ID = UUID("00000000-0000-0000-0000-000000000010")


def policy(mode: str = "warn", token_limit: int | None = 5000) -> ModelPolicyContext:
    now = datetime.now(UTC)
    return ModelPolicyContext(
        id=POLICY_ID,
        project_id=PRINCIPAL.project_id,
        provider="ollama",
        model="qwen2.5:0.5b",
        mode=mode,
        token_limit=token_limit,
        created_at=now,
        updated_at=now,
    )


class FakeModelPolicyService:
    async def list(self, principal):  # type: ignore[no-untyped-def]
        assert principal == PRINCIPAL
        return [policy()]

    async def upsert(self, principal, body):  # type: ignore[no-untyped-def]
        assert principal == PRINCIPAL
        assert body.provider == "ollama"
        assert body.model == "qwen2.5:0.5b"
        return policy(body.mode.value, body.token_limit)


def build_app() -> FastAPI:
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_principal] = lambda: PRINCIPAL
    application.dependency_overrides[get_model_policy_service] = FakeModelPolicyService
    return application


@pytest.mark.asyncio
async def test_list_model_policies_is_project_scoped() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/model-policies")

    assert response.status_code == 200
    assert response.json()[0]["project_id"] == str(PRINCIPAL.project_id)


@pytest.mark.asyncio
async def test_upsert_model_policy_uses_typed_body() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()), base_url="http://test"
    ) as client:
        response = await client.put(
            "/api/v1/model-policies",
            json={
                "provider": "ollama",
                "model": "qwen2.5:0.5b",
                "mode": "block",
                "token_limit": 8000,
            },
        )

    assert response.status_code == 200
    assert response.json()["mode"] == "block"
    assert response.json()["token_limit"] == 8000


@pytest.mark.asyncio
async def test_model_policy_rejects_invalid_provider_and_zero_limit() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()), base_url="http://test"
    ) as client:
        response = await client.put(
            "/api/v1/model-policies",
            json={
                "provider": "https://paid.example",
                "model": "paid-model",
                "mode": "block",
                "token_limit": 0,
            },
        )

    assert response.status_code == 422
