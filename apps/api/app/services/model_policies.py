from control_schemas import ModelPolicyContext, ModelPolicyUpsert

from app.domain.auth import ApiKeyPrincipal
from app.repositories.model_policies import ModelPolicyRepository


class ModelPolicyService:
    def __init__(self, repository: ModelPolicyRepository) -> None:
        self._repository = repository

    async def list(self, principal: ApiKeyPrincipal) -> list[ModelPolicyContext]:
        return await self._repository.list(principal.project_id)

    async def upsert(
        self,
        principal: ApiKeyPrincipal,
        policy: ModelPolicyUpsert,
    ) -> ModelPolicyContext:
        return await self._repository.upsert(
            organization_id=principal.organization_id,
            project_id=principal.project_id,
            api_key_id=principal.api_key_id,
            policy=policy,
        )
