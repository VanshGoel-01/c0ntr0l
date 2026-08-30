from typing import Annotated

from control_schemas import ChatCompletion, ChatRequest
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_chat_service, get_principal
from app.domain.auth import ApiKeyPrincipal
from app.providers.errors import (
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.services.chat import ChatService

router = APIRouter(prefix="/v1", tags=["chat"])
PrincipalDependency = Annotated[ApiKeyPrincipal, Depends(get_principal)]
ChatServiceDependency = Annotated[ChatService, Depends(get_chat_service)]
RequestIdHeader = Annotated[
    str | None,
    Header(alias="X-Request-Id", min_length=1, max_length=128),
]
DemoScenarioHeader = Annotated[
    str | None,
    Header(alias="X-Control-Demo-Scenario", min_length=1, max_length=32),
]
ApplicationHeader = Annotated[
    str | None,
    Header(alias="X-Control-Application", min_length=1, max_length=63),
]
AgentHeader = Annotated[
    str | None,
    Header(alias="X-Control-Agent", min_length=1, max_length=63),
]


@router.post(
    "/chat/completions",
    operation_id="createChatCompletion",
    response_model=ChatCompletion,
)
async def create_chat_completion(
    body: ChatRequest,
    response: Response,
    request: Request,
    principal: PrincipalDependency,
    service: ChatServiceDependency,
    request_id: RequestIdHeader = None,
    demo_scenario: DemoScenarioHeader = None,
    application_slug: ApplicationHeader = None,
    agent_slug: AgentHeader = None,
) -> ChatCompletion | StreamingResponse:
    settings = request.app.state.settings
    if demo_scenario is not None and not settings.allow_demo_scenarios:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Demo scenarios are disabled",
        )
    try:
        if body.stream:
            stream = await service.stream(
                principal,
                body,
                request_id=request_id,
                demo_scenario=demo_scenario,
                application_slug=application_slug,
                agent_slug=agent_slug,
            )
            return StreamingResponse(
                stream.events,
                media_type="text/event-stream",
                headers={
                    "X-Control-Execution-Id": stream.execution_id,
                    "Cache-Control": "no-store",
                    "X-Accel-Buffering": "no",
                },
            )
        result = await service.complete(
            principal,
            body,
            request_id=request_id,
            demo_scenario=demo_scenario,
            application_slug=application_slug,
            agent_slug=agent_slug,
        )
    except ProviderTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The model provider timed out",
        ) from exc
    except ProviderUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The model provider is unavailable",
        ) from exc
    except ProviderResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The model provider returned an invalid response",
        ) from exc

    response.headers["X-Control-Execution-Id"] = result.execution_id
    response.headers["Cache-Control"] = "no-store"
    return result.completion
