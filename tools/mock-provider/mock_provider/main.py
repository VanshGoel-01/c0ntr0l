from fastapi import FastAPI

from mock_provider.api.router import api_router
from mock_provider.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    application = FastAPI(
        title="c0ntr0l Mock Provider",
        version=resolved_settings.service_version,
    )
    application.state.settings = resolved_settings
    application.include_router(api_router)
    return application


app = create_app()
