from typing import Annotated

from control_schemas import HealthResponse
from fastapi import APIRouter, Depends

from app.api.dependencies import get_health_service
from app.services.health import HealthService

router = APIRouter(tags=["health"])
HealthServiceDependency = Annotated[HealthService, Depends(get_health_service)]


@router.get("/health", operation_id="getHealth", response_model=HealthResponse)
async def get_health(service: HealthServiceDependency) -> HealthResponse:
    return await service.check()
