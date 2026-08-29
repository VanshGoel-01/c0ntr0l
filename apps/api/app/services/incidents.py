from uuid import UUID

from control_schemas import IncidentContext, IncidentStatus

from app.domain.auth import ApiKeyPrincipal
from app.repositories.incidents import IncidentRepository


class IncidentService:
    def __init__(self, repository: IncidentRepository) -> None:
        self._repository = repository

    async def list(
        self,
        principal: ApiKeyPrincipal,
        *,
        limit: int,
        status: IncidentStatus | None,
    ) -> list[IncidentContext]:
        return await self._repository.list(
            principal.project_id,
            limit=limit,
            status=status,
        )

    async def update_status(
        self,
        principal: ApiKeyPrincipal,
        incident_id: UUID,
        status: IncidentStatus,
    ) -> IncidentContext:
        return await self._repository.update_status(
            principal.project_id,
            incident_id,
            status,
        )
