from pathlib import Path

import yaml
from app.api.router import api_router
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[3]


def load_contract() -> dict[str, object]:
    with (ROOT / "docs" / "contracts" / "openapi.yaml").open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def test_checked_in_contract_matches_implemented_operations() -> None:
    application = FastAPI()
    application.include_router(api_router)
    generated = application.openapi()
    contract = load_contract()

    expected_operations = {
        ("/health", "get"),
        ("/v1/chat/completions", "post"),
        ("/api/v1/executions", "get"),
        ("/api/v1/executions/{execution_id}", "get"),
        ("/api/v1/events", "get"),
        ("/api/v1/workspace", "get"),
        ("/api/v1/incidents", "get"),
        ("/api/v1/incidents/{incident_id}", "patch"),
        ("/api/v1/model-policies", "get"),
        ("/api/v1/model-policies", "put"),
        ("/api/v1/providers", "get"),
        ("/api/v1/runtime/executions", "post"),
        ("/api/v1/runtime/executions/{execution_id}/preflight", "post"),
        ("/api/v1/runtime/executions/{execution_id}/actions/check", "post"),
        (
            "/api/v1/runtime/executions/{execution_id}/actions/{action_id}/complete",
            "post",
        ),
        ("/api/v1/runtime/executions/{execution_id}/intervention", "get"),
        ("/api/v1/runtime/executions/{execution_id}/cancel", "post"),
        ("/api/v1/runtime/executions/{execution_id}/recover", "post"),
    }
    assert {
        (path, method)
        for path, path_item in contract["paths"].items()
        for method in path_item
    } == expected_operations
    for path, method in expected_operations:
        assert (
            contract["paths"][path][method]["operationId"]
            == generated["paths"][path][method]["operationId"]
        )


def test_contract_documents_authentication_and_current_streaming_default() -> None:
    contract = load_contract()

    assert contract["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    assert (
        contract["components"]["schemas"]["ChatRequest"]["properties"]["stream"][
            "default"
        ]
        is False
    )
    assert (
        contract["paths"]["/api/v1/runtime/executions/{execution_id}/actions/check"][
            "post"
        ]["operationId"]
        == "checkRuntimeAction"
    )
    assert (
        contract["paths"]["/v1/chat/completions"]["post"]["responses"]["403"][
            "description"
        ]
        == "The project model policy blocked the provider call"
    )
