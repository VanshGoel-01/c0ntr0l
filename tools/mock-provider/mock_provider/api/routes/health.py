from typing import Annotated

from fastapi import APIRouter, Depends

from mock_provider.api.dependencies import get_settings
from mock_provider.core.config import Settings

router = APIRouter(tags=["health"])
SettingsDependency = Annotated[Settings, Depends(get_settings)]


@router.get("/health", operation_id="getMockProviderHealth")
async def health(settings: SettingsDependency) -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.service_version,
    }
