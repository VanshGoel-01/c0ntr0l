import asyncio

from control_schemas import DependencyHealth, DependencyStatus
from sqlalchemy import text

from app.infrastructure.database import Database


class PostgresProbe:
    name = "postgres"

    def __init__(self, database: Database, timeout_seconds: float = 3.0) -> None:
        self._database = database
        self._timeout_seconds = timeout_seconds

    async def check(self) -> DependencyHealth:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._database.connect() as connection:
                    await connection.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 - probes convert any driver failure into health data
            return DependencyHealth(
                status=DependencyStatus.UNHEALTHY,
                detail=f"Database probe failed ({type(exc).__name__})",
            )
        return DependencyHealth(status=DependencyStatus.HEALTHY)

    async def close(self) -> None:
        await self._database.close()
