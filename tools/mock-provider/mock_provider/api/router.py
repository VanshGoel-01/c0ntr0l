from fastapi import APIRouter

from mock_provider.api.routes.chat import router as chat_router
from mock_provider.api.routes.health import router as health_router
from mock_provider.api.routes.models import router as models_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(models_router)
api_router.include_router(chat_router)
