from fastapi import APIRouter

from app.api.routes.chat import router as chat_router
from app.api.routes.events import router as events_router
from app.api.routes.executions import router as executions_router
from app.api.routes.health import router as health_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.runtime import router as runtime_router
from app.api.routes.workspace import router as workspace_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(chat_router)
api_router.include_router(events_router)
api_router.include_router(executions_router)
api_router.include_router(incidents_router)
api_router.include_router(workspace_router)
api_router.include_router(runtime_router)
