from typing import Any, TypeVar
from uuid import UUID

import httpx
from control_schemas import (
    RecoveryStrategy,
    RuntimeActionCheckRequest,
    RuntimeActionCompleteRequest,
    RuntimeActionCompleted,
    RuntimeActionDecision,
    RuntimeCancellationResult,
    RuntimeExecutionCreated,
    RuntimeExecutionRequest,
    RuntimeIntervention,
    RuntimePreflightRequest,
    RuntimePreflightResult,
    RuntimeRecoveryRequest,
    RuntimeRecoveryResult,
)
from pydantic import BaseModel, ValidationError

from control_sdk.errors import (
    ControlApiError,
    ControlProtocolError,
    ControlTransportError,
)

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class ControlRuntimeClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 10.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = http_client is None
        self._authorization = f"Bearer {api_key}"
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": self._authorization},
            timeout=timeout,
        )

    async def __aenter__(self) -> "ControlRuntimeClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def start_execution(
        self, request: RuntimeExecutionRequest
    ) -> RuntimeExecutionCreated:
        return await self._request(
            "POST",
            "/api/v1/runtime/executions",
            RuntimeExecutionCreated,
            json=request.model_dump(mode="json"),
        )

    async def check_action(
        self,
        execution_id: UUID,
        request: RuntimeActionCheckRequest,
    ) -> RuntimeActionDecision:
        return await self._request(
            "POST",
            f"/api/v1/runtime/executions/{execution_id}/actions/check",
            RuntimeActionDecision,
            json=request.model_dump(mode="json"),
        )

    async def preflight_model_call(
        self,
        execution_id: UUID,
        request: RuntimePreflightRequest,
    ) -> RuntimePreflightResult:
        return await self._request(
            "POST",
            f"/api/v1/runtime/executions/{execution_id}/preflight",
            RuntimePreflightResult,
            json=request.model_dump(mode="json"),
        )

    async def complete_action(
        self,
        execution_id: UUID,
        action_id: UUID,
        request: RuntimeActionCompleteRequest,
    ) -> RuntimeActionCompleted:
        return await self._request(
            "POST",
            (
                f"/api/v1/runtime/executions/{execution_id}/actions/"
                f"{action_id}/complete"
            ),
            RuntimeActionCompleted,
            json=request.model_dump(mode="json"),
        )

    async def get_intervention(self, execution_id: UUID) -> RuntimeIntervention:
        return await self._request(
            "GET",
            f"/api/v1/runtime/executions/{execution_id}/intervention",
            RuntimeIntervention,
        )

    async def cancel_execution(
        self, execution_id: UUID
    ) -> RuntimeCancellationResult:
        return await self._request(
            "POST",
            f"/api/v1/runtime/executions/{execution_id}/cancel",
            RuntimeCancellationResult,
        )

    async def recover_execution(
        self,
        execution_id: UUID,
        *,
        strategy: RecoveryStrategy,
        target_provider: str | None = None,
        target_model: str | None = None,
        modified_arguments: dict[str, Any] | None = None,
    ) -> RuntimeRecoveryResult:
        request = RuntimeRecoveryRequest(
            strategy=strategy,
            target_provider=target_provider,
            target_model=target_model,
            modified_arguments=modified_arguments,
        )
        return await self._request(
            "POST",
            f"/api/v1/runtime/executions/{execution_id}/recover",
            RuntimeRecoveryResult,
            json=request.model_dump(mode="json"),
        )

    async def _request(
        self,
        method: str,
        path: str,
        response_model: type[ResponseModel],
        **kwargs: Any,
    ) -> ResponseModel:
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = self._authorization
        try:
            response = await self._client.request(
                method, path, headers=headers, **kwargs
            )
        except httpx.HTTPError as exc:
            raise ControlTransportError(
                f"Could not reach the c0ntr0l API: {exc}"
            ) from exc

        if response.is_error:
            raise ControlApiError(response.status_code, _response_detail(response))

        try:
            return response_model.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise ControlProtocolError(
                f"Invalid response for {method} {path}"
            ) from exc


def _response_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:500] or "Unknown API error"

    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail
    return "Unknown API error"
