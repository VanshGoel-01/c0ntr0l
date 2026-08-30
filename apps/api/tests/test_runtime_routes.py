from datetime import UTC, datetime
from uuid import UUID

import pytest
from app.api.dependencies import get_principal, get_runtime_service
from app.api.routes.runtime import router
from app.domain.auth import ApiKeyPrincipal
from control_schemas import (
    RuntimeActionDecision,
    RuntimeDecision,
    RuntimeExecutionCreated,
    RuntimePolicyMode,
    RuntimePreflightResult,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

PRINCIPAL = ApiKeyPrincipal(
    api_key_id=UUID("00000000-0000-0000-0000-000000000001"),
    organization_id=UUID("00000000-0000-0000-0000-000000000002"),
    project_id=UUID("00000000-0000-0000-0000-000000000003"),
)
EXECUTION_ID = UUID("00000000-0000-0000-0000-000000000010")
ACTION_ID = UUID("00000000-0000-0000-0000-000000000011")


class FakeRuntimeService:
    async def start(self, principal, request):  # type: ignore[no-untyped-def]
        assert principal == PRINCIPAL
        return RuntimeExecutionCreated(
            execution_id=EXECUTION_ID,
            trace_id="run_test",
            status="running",
            repeat_threshold=request.repeat_threshold,
            policy_mode=request.policy_mode,
        )

    async def check_action(self, principal, execution_id, request):  # type: ignore[no-untyped-def]
        assert principal == PRINCIPAL
        assert execution_id == EXECUTION_ID
        return RuntimeActionDecision(
            execution_id=execution_id,
            action_id=ACTION_ID,
            decision=RuntimeDecision.BLOCK,
            operation_fingerprint="a" * 64,
            occurrence=4,
            threshold=3,
            reason="Repeated action produced no meaningful progress",
            evidence={"identical_results": True},
            checkpoint_id=UUID("00000000-0000-0000-0000-000000000012"),
        )

    async def preflight(self, principal, execution_id, request):  # type: ignore[no-untyped-def]
        return RuntimePreflightResult(
            execution_id=execution_id,
            decision=RuntimeDecision.WARN,
            reason="Projected request is approaching the model context limit",
            provider="mock",
            model="mock-model",
            input_tokens=request.input_tokens,
            reserved_output_tokens=request.requested_output_tokens,
            safety_margin_tokens=256,
            projected_context_tokens=7_500,
            context_window_tokens=8_192,
            context_remaining_tokens=692,
            context_utilization=0.9155,
        )


def build_app() -> FastAPI:
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_principal] = lambda: PRINCIPAL
    application.dependency_overrides[get_runtime_service] = FakeRuntimeService
    return application


@pytest.mark.asyncio
async def test_start_runtime_execution_uses_typed_policy_configuration() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/runtime/executions",
            json={
                "task": "Research watershed monitoring",
                "model": "gemma3:4b",
                "repeat_threshold": 3,
                "policy_mode": "enforce",
            },
        )

    assert response.status_code == 201
    assert response.json()["execution_id"] == str(EXECUTION_ID)
    assert response.json()["policy_mode"] == RuntimePolicyMode.ENFORCE


@pytest.mark.asyncio
async def test_blocked_action_returns_evidence_and_control_headers() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/runtime/executions/{EXECUTION_ID}/actions/check",
            json={
                "kind": "tool",
                "name": "search",
                "arguments": {"query": "Indian watershed monitoring"},
            },
        )

    assert response.status_code == 200
    assert response.headers["x-control-decision"] == "block"
    assert response.json()["evidence"]["identical_results"] is True
    assert datetime.now(UTC).tzinfo is not None


@pytest.mark.asyncio
async def test_modified_retry_requires_new_arguments() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/runtime/executions/{EXECUTION_ID}/recover",
            json={"strategy": "retry_modified"},
        )

    assert response.status_code == 422
    assert "modified_arguments are required" in response.text


@pytest.mark.asyncio
async def test_preflight_returns_control_decision_header() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/runtime/executions/{EXECUTION_ID}/preflight",
            json={"input_tokens": 7000, "requested_output_tokens": 244},
        )

    assert response.status_code == 200
    assert response.headers["x-control-decision"] == "warn"
    assert response.json()["context_window_tokens"] == 8192
