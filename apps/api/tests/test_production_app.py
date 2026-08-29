from app.core.config import Settings
from app.main import create_app


def test_production_disables_interactive_api_documentation() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+asyncpg://user:password@localhost/database",
        redis_url="redis://localhost:6379/0",
        api_key_pepper="production-test-pepper",
        allow_demo_scenarios=False,
    )

    application = create_app(settings)

    assert application.docs_url is None
    assert application.redoc_url is None
    assert application.openapi_url is None
