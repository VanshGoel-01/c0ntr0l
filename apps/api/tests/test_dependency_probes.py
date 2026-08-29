import pytest
from app.infrastructure.database import Database
from app.infrastructure.postgres import PostgresProbe
from app.infrastructure.redis import RedisProbe
from control_schemas import DependencyStatus


@pytest.mark.asyncio
async def test_postgres_probe_returns_sanitized_failure() -> None:
    database = Database("postgresql+asyncpg://user:secret@127.0.0.1:1/database")
    probe = PostgresProbe(database, timeout_seconds=0.1)

    result = await probe.check()
    await probe.close()

    assert result.status is DependencyStatus.UNHEALTHY
    assert "secret" not in (result.detail or "")


@pytest.mark.asyncio
async def test_redis_probe_returns_sanitized_failure() -> None:
    probe = RedisProbe("redis://:secret@127.0.0.1:1/0", timeout_seconds=0.1)

    result = await probe.check()
    await probe.close()

    assert result.status is DependencyStatus.UNHEALTHY
    assert "secret" not in (result.detail or "")
