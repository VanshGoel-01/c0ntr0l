from typing import Annotated

from control_schemas import WorkspaceContext
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_principal, get_workspace_service
from app.domain.auth import ApiKeyPrincipal
from app.services.workspace import WorkspaceService

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])
PrincipalDependency = Annotated[ApiKeyPrincipal, Depends(get_principal)]
WorkspaceServiceDependency = Annotated[WorkspaceService, Depends(get_workspace_service)]


@router.get("", operation_id="getWorkspace", response_model=WorkspaceContext)
async def get_workspace(
    principal: PrincipalDependency,
    service: WorkspaceServiceDependency,
) -> WorkspaceContext:
    workspace = await service.get(principal)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )
    return workspace
