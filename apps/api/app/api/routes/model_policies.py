from typing import Annotated

from control_schemas import ModelPolicyContext, ModelPolicyUpsert
from fastapi import APIRouter, Depends

from app.api.dependencies import get_model_policy_service, get_principal
from app.domain.auth import ApiKeyPrincipal
from app.services.model_policies import ModelPolicyService

router = APIRouter(prefix="/api/v1/model-policies", tags=["model-policies"])
PrincipalDependency = Annotated[ApiKeyPrincipal, Depends(get_principal)]
ModelPolicyServiceDependency = Annotated[
    ModelPolicyService,
    Depends(get_model_policy_service),
]


@router.get(
    "", operation_id="listModelPolicies", response_model=list[ModelPolicyContext]
)
async def list_model_policies(
    principal: PrincipalDependency,
    service: ModelPolicyServiceDependency,
) -> list[ModelPolicyContext]:
    return await service.list(principal)


@router.put("", operation_id="upsertModelPolicy", response_model=ModelPolicyContext)
async def upsert_model_policy(
    body: ModelPolicyUpsert,
    principal: PrincipalDependency,
    service: ModelPolicyServiceDependency,
) -> ModelPolicyContext:
    return await service.upsert(principal, body)
