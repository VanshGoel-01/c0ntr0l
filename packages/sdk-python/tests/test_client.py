from uuid import UUID

import httpx
import pytest
from control_schemas import RuntimeExecutionRequest

from control_sdk import ControlApiError, ControlRuntimeClient

EXECUTION_ID = "00000000-0000-0000-0000-000000000010"


@pytest.mark.asyncio
async def test_client_sends_bearer_key_and_parses_execution() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer ctl_test"
        assert request.url.path == "/api/v1/runtime/executions"
        return httpx.Response(
            201,
            json={
                "execution_id": EXECUTION_ID,
                "trace_id": "run_sdk",
                "status": "running",
                "repeat_threshold": 3,
                "policy_mode": "enforce",
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://control.test",
    ) as http_client:
        client = ControlRuntimeClient(
            base_url="http://control.test",
            api_key="ctl_test",
            http_client=http_client,
        )
        execution = await client.start_execution(
            RuntimeExecutionRequest(task="Test SDK", model="mock-model")
        )

    assert execution.execution_id == UUID(EXECUTION_ID)
    assert execution.trace_id == "run_sdk"


@pytest.mark.asyncio
async def test_client_raises_typed_api_error() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "Execution is blocked"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://control.test"
    ) as http_client:
        client = ControlRuntimeClient(
            base_url="http://control.test",
            api_key="ctl_test",
            http_client=http_client,
        )
        with pytest.raises(ControlApiError) as error:
            await client.start_execution(
                RuntimeExecutionRequest(task="Test SDK", model="mock-model")
            )

    assert error.value.status_code == 409
    assert error.value.detail == "Execution is blocked"
