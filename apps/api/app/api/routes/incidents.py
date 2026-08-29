from typing import Annotated
from uuid import UUID

from control_schemas import IncidentContext, IncidentStatus, IncidentStatusUpdate
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_incident_service, get_principal
from app.domain.auth import ApiKeyPrincipal
from app.repositories.incidents import IncidentNotFoundError
from app.services.incidents import IncidentService

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])
PrincipalDependency = Annotated[ApiKeyPrincipal, Depends(get_principal)]
IncidentServiceDependency = Annotated[IncidentService, Depends(get_incident_service)]


@router.get("", operation_id="listIncidents", response_model=list[IncidentContext])
async def list_incidents(
    principal: PrincipalDependency,
    service: IncidentServiceDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    incident_status: Annotated[IncidentStatus | None, Query(alias="status")] = None,
) -> list[IncidentContext]:
    return await service.list(principal, limit=limit, status=incident_status)


@router.patch(
    "/{incident_id}",
    operation_id="updateIncidentStatus",
    response_model=IncidentContext,
)
async def update_incident_status(
    incident_id: UUID,
    body: IncidentStatusUpdate,
    principal: PrincipalDependency,
    service: IncidentServiceDependency,
) -> IncidentContext:
    try:
        return await service.update_status(principal, incident_id, body.status)
    except IncidentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        ) from exc
