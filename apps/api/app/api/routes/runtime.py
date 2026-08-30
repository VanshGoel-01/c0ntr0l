from typing import Annotated
from uuid import UUID

from control_schemas import (
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
from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import get_principal, get_runtime_service
from app.domain.auth import ApiKeyPrincipal
from app.repositories.runtime import (
    RuntimeActionNotFoundError,
    RuntimeExecutionNotActiveError,
    RuntimeExecutionNotFoundError,
    RuntimeRecoveryError,
)
from app.services.runtime import RuntimeService

router = APIRouter(prefix="/api/v1/runtime/executions", tags=["runtime"])
PrincipalDependency = Annotated[ApiKeyPrincipal, Depends(get_principal)]
RuntimeServiceDependency = Annotated[RuntimeService, Depends(get_runtime_service)]


@router.post(
    "",
    operation_id="startRuntimeExecution",
    response_model=RuntimeExecutionCreated,
    status_code=status.HTTP_201_CREATED,
)
async def start_runtime_execution(
    body: RuntimeExecutionRequest,
    principal: PrincipalDependency,
    service: RuntimeServiceDependency,
) -> RuntimeExecutionCreated:
    return await service.start(principal, body)


@router.post(
    "/{execution_id}/preflight",
    operation_id="preflightRuntimeModelCall",
    response_model=RuntimePreflightResult,
)
async def preflight_runtime_model_call(
    execution_id: UUID,
    body: RuntimePreflightRequest,
    response: Response,
    principal: PrincipalDependency,
    service: RuntimeServiceDependency,
) -> RuntimePreflightResult:
    try:
        result = await service.preflight(principal, execution_id, body)
    except (
        RuntimeExecutionNotFoundError,
        RuntimeExecutionNotActiveError,
    ) as exc:
        _raise_runtime_error(exc)
    response.headers["X-Control-Execution-Id"] = str(execution_id)
    response.headers["X-Control-Decision"] = result.decision.value
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post(
    "/{execution_id}/actions/check",
    operation_id="checkRuntimeAction",
    response_model=RuntimeActionDecision,
)
async def check_runtime_action(
    execution_id: UUID,
    body: RuntimeActionCheckRequest,
    response: Response,
    principal: PrincipalDependency,
    service: RuntimeServiceDependency,
) -> RuntimeActionDecision:
    try:
        decision = await service.check_action(principal, execution_id, body)
    except (
        RuntimeExecutionNotFoundError,
        RuntimeExecutionNotActiveError,
    ) as exc:
        _raise_runtime_error(exc)
    response.headers["X-Control-Execution-Id"] = str(execution_id)
    response.headers["X-Control-Decision"] = decision.decision.value
    response.headers["Cache-Control"] = "no-store"
    return decision


@router.post(
    "/{execution_id}/actions/{action_id}/complete",
    operation_id="completeRuntimeAction",
    response_model=RuntimeActionCompleted,
)
async def complete_runtime_action(
    execution_id: UUID,
    action_id: UUID,
    body: RuntimeActionCompleteRequest,
    principal: PrincipalDependency,
    service: RuntimeServiceDependency,
) -> RuntimeActionCompleted:
    try:
        return await service.complete_action(
            principal, execution_id, action_id, body
        )
    except (
        RuntimeExecutionNotFoundError,
        RuntimeExecutionNotActiveError,
        RuntimeActionNotFoundError,
    ) as exc:
        _raise_runtime_error(exc)


@router.get(
    "/{execution_id}/intervention",
    operation_id="getRuntimeIntervention",
    response_model=RuntimeIntervention,
)
async def get_runtime_intervention(
    execution_id: UUID,
    principal: PrincipalDependency,
    service: RuntimeServiceDependency,
) -> RuntimeIntervention:
    try:
        intervention = await service.get_intervention(principal, execution_id)
    except RuntimeExecutionNotFoundError as exc:
        _raise_runtime_error(exc)
    if intervention is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No runtime intervention exists for this execution",
        )
    return intervention


@router.post(
    "/{execution_id}/cancel",
    operation_id="cancelRuntimeExecution",
    response_model=RuntimeCancellationResult,
)
async def cancel_runtime_execution(
    execution_id: UUID,
    principal: PrincipalDependency,
    service: RuntimeServiceDependency,
) -> RuntimeCancellationResult:
    try:
        return await service.cancel(principal, execution_id)
    except (
        RuntimeExecutionNotFoundError,
        RuntimeExecutionNotActiveError,
    ) as exc:
        _raise_runtime_error(exc)


@router.post(
    "/{execution_id}/recover",
    operation_id="recoverRuntimeExecution",
    response_model=RuntimeRecoveryResult,
)
async def recover_runtime_execution(
    execution_id: UUID,
    body: RuntimeRecoveryRequest,
    principal: PrincipalDependency,
    service: RuntimeServiceDependency,
) -> RuntimeRecoveryResult:
    try:
        return await service.recover(principal, execution_id, body)
    except (
        RuntimeExecutionNotFoundError,
        RuntimeRecoveryError,
    ) as exc:
        _raise_runtime_error(exc)


def _raise_runtime_error(exc: Exception) -> None:
    if isinstance(exc, (RuntimeExecutionNotFoundError, RuntimeActionNotFoundError)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Runtime execution or action not found",
        ) from exc
    if isinstance(exc, RuntimeExecutionNotActiveError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Runtime execution is already {exc.status}",
        ) from exc
    if isinstance(exc, RuntimeRecoveryError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    raise exc
