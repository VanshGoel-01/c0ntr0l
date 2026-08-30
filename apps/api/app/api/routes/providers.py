from typing import Annotated

from control_schemas import ProviderCatalog
from fastapi import APIRouter, Depends

from app.api.dependencies import get_principal, get_provider_registry
from app.domain.auth import ApiKeyPrincipal
from app.providers.registry import ProviderRegistry

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])
PrincipalDependency = Annotated[ApiKeyPrincipal, Depends(get_principal)]
RegistryDependency = Annotated[ProviderRegistry, Depends(get_provider_registry)]


@router.get("", operation_id="listProviders", response_model=ProviderCatalog)
async def list_providers(
    principal: PrincipalDependency,
    registry: RegistryDependency,
) -> ProviderCatalog:
    del principal
    return await registry.catalog()
