from uuid import UUID

import httpx
import pytest
from control_cli.client import ControlApiError, ControlClient
from control_cli.config import CliConfig

KEY = "ctl_" + "a" * 40
CONFIG = CliConfig(api_url="https://control.example.com", api_key=KEY)
PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000002")


def workspace_payload() -> dict[str, object]:
    return {
        "organization_id": str(ORGANIZATION_ID),
        "organization_name": "Acme",
        "project_id": str(PROJECT_ID),
        "project_slug": "research",
        "project_name": "Research",
        "applications": [],
        "budgets": [],
        "requests_24h": 4,
        "tokens_24h": 1200,
        "cost_24h": "0",
    }


def test_client_sends_project_key_and_validates_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        assert request.headers["User-Agent"] == "c0ntr0l-cli/0.1.0"
        return httpx.Response(200, json=workspace_payload())

    with ControlClient(CONFIG, transport=httpx.MockTransport(handler)) as client:
        workspace = client.workspace()

    assert workspace.project_id == PROJECT_ID
    assert workspace.requests_24h == 4


def test_client_refuses_redirects_before_credentials_can_be_forwarded() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            307,
            headers={"Location": "https://attacker.example.com/collect"},
        )
    )

    with (
        ControlClient(CONFIG, transport=transport) as client,
        pytest.raises(ControlApiError, match="redirects are refused"),
    ):
        client.workspace()


def test_client_redacts_project_keys_from_api_errors() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            400,
            json={"detail": f"The submitted key {KEY} is invalid"},
        )
    )

    with (
        ControlClient(CONFIG, transport=transport) as client,
        pytest.raises(ControlApiError) as error,
    ):
        client.workspace()

    assert KEY not in str(error.value)
    assert "[redacted]" in str(error.value)


def test_client_rejects_malformed_success_payload() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"project_name": "Incomplete"})
    )

    with (
        ControlClient(CONFIG, transport=transport) as client,
        pytest.raises(ControlApiError, match="malformed data"),
    ):
        client.workspace()
