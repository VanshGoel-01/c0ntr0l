from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.domain.auth import ApiKeyPrincipal, InvalidApiKeyError
from app.infrastructure.execution_events import ExecutionEvents
from app.services.authentication import AuthenticationService
from app.services.chat import ChatService
from app.services.executions import ExecutionQueryService
from app.services.health import HealthService
from app.services.incidents import IncidentService
from app.services.runtime import RuntimeService
from app.services.workspace import WorkspaceService

bearer_scheme = HTTPBearer(auto_error=False, scheme_name="bearerAuth")


def get_health_service(request: Request) -> HealthService:
    return request.app.state.health_service


def get_authentication_service(request: Request) -> AuthenticationService:
    return request.app.state.authentication_service


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


def get_execution_query_service(request: Request) -> ExecutionQueryService:
    return request.app.state.execution_query_service


def get_workspace_service(request: Request) -> WorkspaceService:
    return request.app.state.workspace_service


def get_incident_service(request: Request) -> IncidentService:
    return request.app.state.incident_service


def get_runtime_service(request: Request) -> RuntimeService:
    return request.app.state.runtime_service


def get_execution_events(request: Request) -> ExecutionEvents:
    return request.app.state.execution_events


async def get_principal(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> ApiKeyPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid project API key is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return await service.authenticate(credentials.credentials)
    except InvalidApiKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid project API key is required",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
