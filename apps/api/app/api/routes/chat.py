from typing import Annotated

from control_schemas import ChatCompletion, ChatRequest
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_chat_service, get_principal
from app.domain.auth import ApiKeyPrincipal
from app.providers.errors import (
    ProviderModelNotFoundError,
    ProviderNotConfiguredError,
    ProviderResponseError,
    ProviderScenarioUnsupportedError,
    ProviderSelectionAmbiguousError,
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
ProviderHeader = Annotated[
    str | None,
    Header(
        alias="X-Control-Provider",
        pattern=r"^(?:auto|[a-z0-9][a-z0-9_-]{0,62})$",
    ),
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
    requested_provider: ProviderHeader = None,
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
                requested_provider=requested_provider,
                application_slug=application_slug,
                agent_slug=agent_slug,
            )
            return StreamingResponse(
                stream.events,
                media_type="text/event-stream",
                headers={
                    "X-Control-Execution-Id": stream.execution_id,
                    "X-Control-Provider": stream.provider_name,
                    "Cache-Control": "no-store",
                    "X-Accel-Buffering": "no",
                },
            )
        result = await service.complete(
            principal,
            body,
            request_id=request_id,
            demo_scenario=demo_scenario,
            requested_provider=requested_provider,
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
    except ProviderModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested model is not installed on an enabled provider",
        ) from exc
    except ProviderSelectionAmbiguousError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The model exists on multiple providers; select X-Control-Provider",
        ) from exc
    except ProviderScenarioUnsupportedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Demo scenarios are supported only by the mock provider",
        ) from exc
    except ProviderNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The requested provider is not enabled",
        ) from exc

    response.headers["X-Control-Execution-Id"] = result.execution_id
    response.headers["X-Control-Provider"] = result.provider_name
    response.headers["Cache-Control"] = "no-store"
    return result.completion
