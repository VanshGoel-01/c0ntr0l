from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.infrastructure.database import Database
from app.infrastructure.execution_events import ExecutionEvents
from app.infrastructure.postgres import PostgresProbe
from app.infrastructure.redis import RedisProbe
from app.infrastructure.runtime_signals import RuntimeSignals
from app.providers.http import HttpProviderClient
from app.providers.ollama import OllamaProviderClient
from app.providers.registry import ProviderRegistry
from app.repositories.api_keys import ApiKeyRepository
from app.repositories.executions import ExecutionRepository
from app.repositories.incidents import IncidentRepository
from app.repositories.model_policies import ModelPolicyRepository
from app.repositories.recovery import RecoveryRepository
from app.repositories.runtime import RuntimeRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.authentication import AuthenticationService
from app.services.chat import ChatService
from app.services.executions import ExecutionQueryService
from app.services.health import HealthService
from app.services.incidents import IncidentService
from app.services.model_policies import ModelPolicyService
from app.services.recovery import RecoveryRunner
from app.services.runtime import RuntimeService
from app.services.workspace import WorkspaceService


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
    ollama_provider = OllamaProviderClient(
        settings.ollama_base_url,
        settings.ollama_timeout_seconds,
    )
    provider_registry = ProviderRegistry(
        {"mock": provider, "ollama": ollama_provider},
        context_defaults={"mock": settings.mock_context_window_tokens},
        catalog_timeout_seconds=settings.provider_catalog_timeout_seconds,
        catalog_ttl_seconds=settings.provider_catalog_ttl_seconds,
    )
    health_service = create_health_service(settings, database)
    authentication_service = AuthenticationService(
        ApiKeyRepository(database),
        settings.api_key_pepper.get_secret_value(),
    )
    execution_repository = ExecutionRepository(database)
    runtime_signals = RuntimeSignals(settings.redis_url)
    execution_events = ExecutionEvents(
        settings.redis_url,
        max_events=settings.event_stream_max_events,
        block_milliseconds=settings.event_stream_block_milliseconds,
    )
    chat_service = ChatService(
        execution_repository, provider_registry, execution_events
    )
    execution_query_service = ExecutionQueryService(execution_repository)
    workspace_service = WorkspaceService(WorkspaceRepository(database))
    incident_service = IncidentService(IncidentRepository(database), execution_events)
    model_policy_service = ModelPolicyService(ModelPolicyRepository(database))
    recovery_runner = RecoveryRunner(
        RecoveryRepository(database),
        provider_registry,
        settings.recovery_max_tokens,
    )
    runtime_service = RuntimeService(
        RuntimeRepository(database),
        runtime_signals,
        recovery_runner,
        provider_registry,
        settings.default_context_window_tokens,
        settings.context_safety_margin_tokens,
        settings.context_warning_utilization,
        execution_events,
    )
    application.state.health_service = health_service
    application.state.authentication_service = authentication_service
    application.state.chat_service = chat_service
    application.state.execution_query_service = execution_query_service
    application.state.workspace_service = workspace_service
    application.state.incident_service = incident_service
    application.state.model_policy_service = model_policy_service
    application.state.runtime_service = runtime_service
    application.state.execution_events = execution_events
    application.state.provider_registry = provider_registry
    try:
        yield
    finally:
        await provider_registry.close()
        await runtime_signals.close()
        await execution_events.close()
        await health_service.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    expose_documentation = resolved_settings.app_env != "production"
    application = FastAPI(
        title="c0ntr0l API",
        version=resolved_settings.service_version,
        lifespan=lifespan,
        docs_url="/docs" if expose_documentation else None,
        redoc_url="/redoc" if expose_documentation else None,
        openapi_url="/openapi.json" if expose_documentation else None,
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
