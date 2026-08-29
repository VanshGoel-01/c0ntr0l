from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.infrastructure.database import Database
from app.infrastructure.postgres import PostgresProbe
from app.infrastructure.redis import RedisProbe
from app.providers.http import HttpProviderClient
from app.repositories.api_keys import ApiKeyRepository
from app.repositories.executions import ExecutionRepository
from app.services.authentication import AuthenticationService
from app.services.chat import ChatService
from app.services.executions import ExecutionQueryService
from app.services.health import HealthService


def create_health_service(settings: Settings, database: Database) -> HealthService:
    return HealthService(
        version=settings.service_version,
        probes=[
            PostgresProbe(database),
            RedisProbe(settings.redis_url),
        ],
    )


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = application.state.settings
    database = Database(settings.database_url)
    provider = HttpProviderClient(
        settings.provider_base_url,
        settings.provider_timeout_seconds,
    )
    health_service = create_health_service(settings, database)
    authentication_service = AuthenticationService(
        ApiKeyRepository(database),
        settings.api_key_pepper.get_secret_value(),
    )
    execution_repository = ExecutionRepository(database)
    chat_service = ChatService(execution_repository, provider)
    execution_query_service = ExecutionQueryService(execution_repository)
    application.state.health_service = health_service
    application.state.authentication_service = authentication_service
    application.state.chat_service = chat_service
    application.state.execution_query_service = execution_query_service
    try:
        yield
    finally:
        await provider.close()
        await health_service.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    application = FastAPI(
        title="c0ntr0l API",
        version=resolved_settings.service_version,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router)
    return application


app = create_app()
