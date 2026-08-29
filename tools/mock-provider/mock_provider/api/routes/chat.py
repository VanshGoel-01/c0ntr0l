import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse

from mock_provider.api.dependencies import get_settings
from mock_provider.contracts import ChatRequest
from mock_provider.core.config import Settings
from mock_provider.scenarios import MockScenario, build_completion, stream_events

router = APIRouter(tags=["chat"])
SettingsDependency = Annotated[Settings, Depends(get_settings)]
ScenarioHeader = Annotated[str | None, Header(alias="X-Mock-Scenario")]


def resolve_scenario(raw_scenario: str | None) -> MockScenario:
    try:
        return MockScenario(raw_scenario or MockScenario.NORMAL)
    except ValueError as exc:
        choices = ", ".join(scenario.value for scenario in MockScenario)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_mock_scenario",
                "message": f"X-Mock-Scenario must be one of: {choices}",
            },
        ) from exc


async def iter_stream(events: list[str]) -> AsyncIterator[str]:
    for event in events:
        yield event
        await asyncio.sleep(0)
    yield "data: [DONE]\n\n"


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"code": code, "message": message, "type": "mock_provider_error"}
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/v1/chat/completions", operation_id="createMockChatCompletion")
async def create_chat_completion(
    request: ChatRequest,
    settings: SettingsDependency,
    raw_scenario: ScenarioHeader = None,
) -> object:
    scenario = resolve_scenario(raw_scenario)

    if scenario is MockScenario.PROVIDER_ERROR:
        return error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "mock_provider_unavailable",
            "The deterministic provider-error scenario was requested.",
        )

    if scenario is MockScenario.TIMEOUT:
        await asyncio.sleep(settings.timeout_delay_seconds)
        return error_response(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "mock_provider_timeout",
            "The deterministic timeout scenario completed its delay.",
        )

    completion = build_completion(request, scenario)
    if request.stream:
        return StreamingResponse(
            iter_stream(stream_events(completion)),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Mock-Scenario": scenario.value,
            },
        )

    return JSONResponse(
        content=completion.model_dump(mode="json"),
        headers={
            "Cache-Control": "no-store",
            "X-Mock-Scenario": scenario.value,
        },
    )
