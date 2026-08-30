from collections.abc import Callable
from typing import Any

import httpx
import pytest
from control_schemas import RuntimeExecutionRequest, RuntimePreflightRequest
from control_sdk import (
    ActionBlockedError,
    ControlledExecution,
    ControlRuntimeClient,
    ModelPreflightBlockedError,
)

EXECUTION_ID = "00000000-0000-0000-0000-000000000010"
ACTION_ID = "00000000-0000-0000-0000-000000000011"
CHECKPOINT_ID = "00000000-0000-0000-0000-000000000012"


def runtime_handler(
    decision: str,
    completed_bodies: list[dict[str, Any]],
) -> Callable[[httpx.Request], httpx.Response]:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/runtime/executions":
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
        if request.url.path.endswith("/actions/check"):
            return httpx.Response(
                200,
                json={
                    "execution_id": EXECUTION_ID,
                    "action_id": ACTION_ID,
                    "decision": decision,
                    "operation_fingerprint": "a" * 64,
                    "occurrence": 3,
                    "threshold": 3,
                    "reason": "Repeated action produced no progress",
                    "evidence": {"identical_results": True},
                    "checkpoint_id": (CHECKPOINT_ID if decision == "block" else None),
                },
            )
        if request.url.path.endswith("/preflight"):
            return httpx.Response(
                200,
                json={
                    "execution_id": EXECUTION_ID,
                    "decision": "block",
                    "reason": "Projected request exceeds the model context window",
                    "provider": "mock",
                    "model": "mock-model",
                    "input_tokens": 8000,
                    "reserved_output_tokens": 512,
                    "safety_margin_tokens": 256,
                    "projected_context_tokens": 8768,
                    "context_window_tokens": 8192,
                    "context_remaining_tokens": 0,
                    "context_utilization": 1.0703,
                    "budgets": [],
                    "checkpoint_id": CHECKPOINT_ID,
                },
            )
        if request.url.path.endswith(f"/actions/{ACTION_ID}/complete"):
            import json

            completed_bodies.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "execution_id": EXECUTION_ID,
                    "action_id": ACTION_ID,
                    "status": completed_bodies[-1]["status"],
                    "result_fingerprint": "b" * 64,
                    "progress": completed_bodies[-1]["progress"],
                },
            )
        return httpx.Response(404, json={"detail": "Not found"})

    return handler


async def build_execution(
    decision: str,
    completed_bodies: list[dict[str, Any]],
) -> tuple[ControlledExecution, httpx.AsyncClient]:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(runtime_handler(decision, completed_bodies)),
        base_url="http://control.test",
    )
    client = ControlRuntimeClient(
        base_url="http://control.test",
        api_key="ctl_test",
        http_client=http_client,
    )
    execution = await ControlledExecution.start(
        client,
        RuntimeExecutionRequest(task="Research watersheds", model="mock-model"),
    )
    return execution, http_client


@pytest.mark.asyncio
async def test_allowed_tool_runs_and_reports_result() -> None:
    completed_bodies: list[dict[str, Any]] = []
    execution, http_client = await build_execution("allow", completed_bodies)

    result = await execution.run_tool(
        name="search",
        arguments={"query": "watershed monitoring"},
        handler=lambda: {"items": ["source-a"]},
        progress=lambda output: bool(output["items"]),
        summary=lambda output: f"Found {len(output['items'])} source",
    )
    await http_client.aclose()

    assert result == {"items": ["source-a"]}
    assert completed_bodies == [
        {
            "status": "completed",
            "result": {"items": ["source-a"]},
            "progress": True,
            "summary": "Found 1 source",
        }
    ]


@pytest.mark.asyncio
async def test_blocked_tool_never_calls_handler() -> None:
    completed_bodies: list[dict[str, Any]] = []
    execution, http_client = await build_execution("block", completed_bodies)
    calls = 0

    def dangerous_tool() -> str:
        nonlocal calls
        calls += 1
        return "should not execute"

    with pytest.raises(ActionBlockedError) as error:
        await execution.run_tool(
            name="search",
            arguments={"query": "watershed monitoring"},
            handler=dangerous_tool,
            progress=False,
        )
    await http_client.aclose()

    assert calls == 0
    assert completed_bodies == []
    assert str(error.value.checkpoint_id) == CHECKPOINT_ID


@pytest.mark.asyncio
async def test_failed_tool_is_reported_without_leaking_error_message() -> None:
    completed_bodies: list[dict[str, Any]] = []
    execution, http_client = await build_execution("allow", completed_bodies)

    def failing_tool() -> str:
        raise RuntimeError("secret provider response")

    with pytest.raises(RuntimeError, match="secret provider response"):
        await execution.run_tool(
            name="search",
            arguments={"query": "watershed monitoring"},
            handler=failing_tool,
            progress=False,
        )
    await http_client.aclose()

    assert completed_bodies[0]["status"] == "failed"
    assert completed_bodies[0]["result"] == {"error_type": "RuntimeError"}
    assert "secret provider response" not in str(completed_bodies[0])


@pytest.mark.asyncio
async def test_model_preflight_block_never_calls_provider_handler() -> None:
    completed_bodies: list[dict[str, Any]] = []
    execution, http_client = await build_execution("allow", completed_bodies)
    calls = 0

    def model_call() -> str:
        nonlocal calls
        calls += 1
        return "should not execute"

    with pytest.raises(ModelPreflightBlockedError) as error:
        await execution.run_model(
            name="chat.completion",
            arguments={"model": "mock-model"},
            handler=model_call,
            progress=True,
            preflight=RuntimePreflightRequest(
                input_tokens=8_000,
                requested_output_tokens=512,
            ),
        )
    await http_client.aclose()

    assert calls == 0
    assert completed_bodies == []
    assert str(error.value.checkpoint_id) == CHECKPOINT_ID
