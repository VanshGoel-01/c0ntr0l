from typing import Annotated

from fastapi import APIRouter, Depends

from mock_provider.api.dependencies import get_settings
from mock_provider.core.config import Settings

router = APIRouter(tags=["models"])
SettingsDependency = Annotated[Settings, Depends(get_settings)]


@router.get("/v1/models", operation_id="listMockModels")
async def list_models(settings: SettingsDependency) -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {
                "id": settings.default_model,
                "object": "model",
                "created": 0,
                "owned_by": "c0ntr0l",
            }
        ],
    }
