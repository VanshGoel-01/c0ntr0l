import argparse
import asyncio
import json
import os
from typing import Any
from urllib.parse import urlparse

import httpx

PROVIDER = "mock"
MODEL = "mock-gpt"


def api_url() -> str:
    value = os.environ.get("CONTROL_API_URL", "http://127.0.0.1:8000").rstrip("/")
    parsed = urlparse(value)
    local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise SystemExit("CONTROL_API_URL must use HTTPS unless it targets localhost")
    return value


def api_key() -> str:
    value = os.environ.get("CONTROL_API_KEY", "")
    if not value.startswith("ctl_") or not 36 <= len(value) <= 64:
        raise SystemExit("Set CONTROL_API_KEY to a valid local project API key")
    return value


async def read_json(response: httpx.Response) -> Any:
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Control API returned invalid JSON ({response.status_code})"
        ) from exc
    if response.is_error:
        detail = body.get("detail") if isinstance(body, dict) else None
        raise RuntimeError(
            str(detail or f"Control API returned {response.status_code}")
        )
    return body


async def set_policy(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    mode: str,
    token_limit: int | None,
) -> None:
    response = await client.put(
        "/api/v1/model-policies",
        headers=headers,
        json={
            "provider": PROVIDER,
            "model": MODEL,
            "mode": mode,
            "token_limit": token_limit,
        },
    )
    await read_json(response)


async def run_demo(*, prepare_only: bool = False) -> dict[str, object]:
    authorization = {"Authorization": f"Bearer {api_key()}"}
    gateway_headers = {**authorization, "X-Control-Provider": PROVIDER}
    timeout = httpx.Timeout(20)
    async with httpx.AsyncClient(
        base_url=api_url(),
        follow_redirects=False,
        timeout=timeout,
    ) as client:
        catalog = await read_json(
            await client.get("/api/v1/providers", headers=authorization)
        )
        routable = any(
            provider.get("name") == PROVIDER
            and provider.get("status") == "operational"
            and MODEL in provider.get("models", [])
            for provider in catalog.get("providers", [])
        )
        if not routable:
            raise RuntimeError("The local mock provider is not operational")

        policies = await read_json(
            await client.get("/api/v1/model-policies", headers=authorization)
        )
        previous = next(
            (
                policy
                for policy in policies
                if policy.get("provider") == PROVIDER and policy.get("model") == MODEL
            ),
            {"mode": "observe", "token_limit": None},  # nosec B105
        )

        try:
            await set_policy(client, authorization, mode="block", token_limit=None)
            blocked = await client.post(
                "/v1/chat/completions",
                headers=gateway_headers,
                json={
                    "model": MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": "Prepare a concise release readiness summary",
                        }
                    ],
                    "max_tokens": 64,
                    "stream": False,
                },
            )
            if blocked.status_code != 403:
                raise RuntimeError(
                    f"Expected policy block, received HTTP {blocked.status_code}"
                )
            execution_id = blocked.headers.get("X-Control-Execution-Id")
            checkpoint_id = blocked.headers.get("X-Control-Checkpoint-Id")
            if not execution_id or not checkpoint_id:
                raise RuntimeError("Blocked response omitted recovery identifiers")

            intervention = await read_json(
                await client.get(
                    f"/api/v1/runtime/executions/{execution_id}/intervention",
                    headers=authorization,
                )
            )
            if intervention.get("checkpoint", {}).get("status") != "available":
                raise RuntimeError("The blocked execution has no available checkpoint")

            await set_policy(client, authorization, mode="observe", token_limit=None)
            if prepare_only:
                return {
                    "blocked_execution_id": execution_id,
                    "checkpoint_id": checkpoint_id,
                    "policy_outcome": intervention.get("outcome"),
                    "provider": PROVIDER,
                    "model": MODEL,
                    "recovery_status": "ready",
                }

            failed_handoff = await read_json(
                await client.post(
                    f"/api/v1/runtime/executions/{execution_id}/recover",
                    headers=authorization,
                    json={
                        "strategy": "model_handoff",
                        "target_provider": "unconfigured-local",
                        "target_model": "missing-model",
                    },
                )
            )
            if failed_handoff.get("status") != "failed":
                raise RuntimeError("The invalid handoff did not fail as expected")
            failed_resumed_id = failed_handoff.get("resumed_execution_id")
            if not failed_resumed_id:
                raise RuntimeError(
                    "The failed handoff omitted its execution identifier"
                )

            restored = await read_json(
                await client.get(
                    f"/api/v1/runtime/executions/{execution_id}/intervention",
                    headers=authorization,
                )
            )
            if restored.get("checkpoint", {}).get("status") != "available":
                raise RuntimeError(
                    "Failed recovery did not restore the source checkpoint"
                )

            recovery = await read_json(
                await client.post(
                    f"/api/v1/runtime/executions/{execution_id}/recover",
                    headers=authorization,
                    json={
                        "strategy": "retry_modified",
                        "modified_arguments": {
                            "instruction": "Continue through the approved local route"
                        },
                    },
                )
            )
            resumed_id = recovery.get("resumed_execution_id")
            if recovery.get("status") != "completed" or not resumed_id:
                raise RuntimeError(
                    "Recovery did not complete through the mock provider"
                )
            resumed = await read_json(
                await client.get(
                    f"/api/v1/executions/{resumed_id}",
                    headers=authorization,
                )
            )
            return {
                "blocked_execution_id": execution_id,
                "checkpoint_id": checkpoint_id,
                "failed_handoff_execution_id": failed_resumed_id,
                "failed_handoff_status": failed_handoff.get("status"),
                "policy_outcome": intervention.get("outcome"),
                "recovery_status": recovery.get("status"),
                "resumed_execution_id": resumed_id,
                "resumed_status": resumed.get("status"),
                "recorded_tokens": resumed.get("total_tokens"),
                "provider": recovery.get("target_provider"),
                "model": recovery.get("target_model"),
            }
        finally:
            await set_policy(
                client,
                authorization,
                mode=str(previous.get("mode", "observe")),
                token_limit=previous.get("token_limit"),
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Demonstrate gateway blocking and checkpoint recovery locally."
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Create a recoverable blocked execution for a web or CLI demonstration.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    print(
        json.dumps(
            asyncio.run(run_demo(prepare_only=arguments.prepare_only)),
            indent=2,
            sort_keys=True,
        )
    )
