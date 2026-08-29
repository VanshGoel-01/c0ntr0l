import re
from typing import Any, Self
from uuid import UUID

import httpx
from control_schemas import (
    ExecutionDetail,
    ExecutionSummary,
    IncidentContext,
    IncidentStatus,
    RuntimeCancellationResult,
    RuntimeIntervention,
    RuntimeRecoveryRequest,
    RuntimeRecoveryResult,
    WorkspaceContext,
)
from pydantic import TypeAdapter, ValidationError

from control_cli.config import CliConfig


class ControlApiError(RuntimeError):
    pass


class ControlClient:
    def __init__(
        self,
        config: CliConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = config.api_key
        self._client = httpx.Client(
            base_url=config.api_url,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Accept": "application/json",
                "User-Agent": "c0ntr0l-cli/0.1.0",
            },
            follow_redirects=False,
            timeout=httpx.Timeout(10.0, connect=3.0),
            transport=transport,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def health(self) -> dict[str, Any]:
        result = self._request("GET", "/health")
        if not isinstance(result, dict):
            raise ControlApiError("Control API returned malformed health data")
        return result

    def workspace(self) -> WorkspaceContext:
        return self._validate(
            WorkspaceContext, self._request("GET", "/api/v1/workspace")
        )

    def executions(self, limit: int) -> list[ExecutionSummary]:
        return self._validate_list(
            ExecutionSummary,
            self._request("GET", "/api/v1/executions", params={"limit": limit}),
        )

    def execution(self, execution_id: UUID) -> ExecutionDetail:
        return self._validate(
            ExecutionDetail,
            self._request("GET", f"/api/v1/executions/{execution_id}"),
        )

    def incidents(
        self, limit: int, status: IncidentStatus | None
    ) -> list[IncidentContext]:
        params: dict[str, object] = {"limit": limit}
        if status is not None:
            params["status"] = status.value
        return self._validate_list(
            IncidentContext,
            self._request("GET", "/api/v1/incidents", params=params),
        )

    def update_incident(
        self, incident_id: UUID, status: IncidentStatus
    ) -> IncidentContext:
        return self._validate(
            IncidentContext,
            self._request(
                "PATCH",
                f"/api/v1/incidents/{incident_id}",
                json={"status": status.value},
            ),
        )

    def intervention(self, execution_id: UUID) -> RuntimeIntervention | None:
        response = self._send(
            "GET", f"/api/v1/runtime/executions/{execution_id}/intervention"
        )
        if response.status_code == 404:
            return None
        return self._validate(RuntimeIntervention, self._response_json(response))

    def cancel(self, execution_id: UUID) -> RuntimeCancellationResult:
        return self._validate(
            RuntimeCancellationResult,
            self._request("POST", f"/api/v1/runtime/executions/{execution_id}/cancel"),
        )

    def recover(
        self, execution_id: UUID, request: RuntimeRecoveryRequest
    ) -> RuntimeRecoveryResult:
        return self._validate(
            RuntimeRecoveryResult,
            self._request(
                "POST",
                f"/api/v1/runtime/executions/{execution_id}/recover",
                json=request.model_dump(mode="json", exclude_none=True),
            ),
        )

    def _request(self, method: str, path: str, **kwargs: object) -> Any:
        return self._response_json(self._send(method, path, **kwargs))

    def _send(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ControlApiError("Control API request timed out") from exc
        except httpx.RequestError as exc:
            raise ControlApiError("Control API is unavailable") from exc

        if response.is_redirect:
            raise ControlApiError(
                "Control API redirects are refused for credential safety"
            )
        if response.is_error:
            detail = "Request failed"
            try:
                payload = response.json()
                if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
                    detail = self._sanitize_detail(payload["detail"])
            except ValueError:
                pass
            raise ControlApiError(
                f"Control API returned {response.status_code}: {detail}"
            )
        return response

    def _sanitize_detail(self, value: str) -> str:
        redacted = value.replace(self._api_key, "[redacted]")
        redacted = re.sub(r"ctl_[A-Za-z0-9_-]{32,60}", "[redacted]", redacted)
        return redacted[:300]

    @staticmethod
    def _response_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise ControlApiError("Control API returned a non-JSON response") from exc

    @staticmethod
    def _validate(model_type, value):  # type: ignore[no-untyped-def]
        try:
            return model_type.model_validate(value)
        except ValidationError as exc:
            raise ControlApiError("Control API returned malformed data") from exc

    @staticmethod
    def _validate_list(model_type, value):  # type: ignore[no-untyped-def]
        try:
            return TypeAdapter(list[model_type]).validate_python(value)
        except ValidationError as exc:
            raise ControlApiError("Control API returned malformed data") from exc
