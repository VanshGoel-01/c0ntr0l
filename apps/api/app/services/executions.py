from uuid import UUID

from control_schemas import ExecutionDetail, ExecutionSummary

from app.domain.auth import ApiKeyPrincipal
from app.repositories.executions import ExecutionRepository


class ExecutionQueryService:
    def __init__(self, repository: ExecutionRepository) -> None:
        self._repository = repository

    async def list_recent(
        self,
        principal: ApiKeyPrincipal,
        limit: int,
    ) -> list[ExecutionSummary]:
        return await self._repository.list_recent(principal.project_id, limit)

    async def get(
        self,
        principal: ApiKeyPrincipal,
        execution_id: UUID,
    ) -> ExecutionDetail | None:
        return await self._repository.get(principal.project_id, execution_id)
