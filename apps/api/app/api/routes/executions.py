from typing import Annotated
from uuid import UUID

from control_schemas import ExecutionDetail, ExecutionSummary
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_execution_query_service, get_principal
from app.domain.auth import ApiKeyPrincipal
from app.services.executions import ExecutionQueryService

router = APIRouter(prefix="/api/v1/executions", tags=["executions"])
PrincipalDependency = Annotated[ApiKeyPrincipal, Depends(get_principal)]
ExecutionServiceDependency = Annotated[
    ExecutionQueryService,
    Depends(get_execution_query_service),
]


@router.get("", operation_id="listExecutions", response_model=list[ExecutionSummary])
async def list_executions(
    principal: PrincipalDependency,
    service: ExecutionServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ExecutionSummary]:
    return await service.list_recent(principal, limit)


@router.get(
    "/{execution_id}",
    operation_id="getExecution",
    response_model=ExecutionDetail,
)
async def get_execution(
    execution_id: UUID,
    principal: PrincipalDependency,
    service: ExecutionServiceDependency,
) -> ExecutionDetail:
    execution = await service.get(principal, execution_id)
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found",
        )
    return execution
