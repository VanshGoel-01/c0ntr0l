from control_schemas import WorkspaceContext

from app.domain.auth import ApiKeyPrincipal
from app.repositories.workspace import WorkspaceRepository


class WorkspaceService:
    def __init__(self, repository: WorkspaceRepository) -> None:
        self._repository = repository

    async def get(self, principal: ApiKeyPrincipal) -> WorkspaceContext | None:
        return await self._repository.get(principal.project_id)
