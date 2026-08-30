from uuid import UUID

from control_schemas import ControlEventType, IncidentContext, IncidentStatus

from app.domain.auth import ApiKeyPrincipal
from app.infrastructure.execution_events import ExecutionEvents
from app.repositories.incidents import IncidentRepository


class IncidentService:
    def __init__(
        self,
        repository: IncidentRepository,
        events: ExecutionEvents | None = None,
    ) -> None:
        self._repository = repository
        self._events = events

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
        result = await self._repository.update_status(
            principal.project_id,
            incident_id,
            status,
        )
        if self._events is not None:
            await self._events.publish(
                principal.project_id,
                ControlEventType.INCIDENT_UPDATED,
                result.execution_id,
            )
        return result
