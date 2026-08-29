import asyncio

from control_schemas import DependencyHealth, DependencyStatus
from redis.asyncio import Redis


class RedisProbe:
    name = "redis"

    def __init__(self, redis_url: str, timeout_seconds: float = 3.0) -> None:
        self._client = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
        )
        self._timeout_seconds = timeout_seconds

    async def check(self) -> DependencyHealth:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                is_ready = await self._client.ping()
        except Exception as exc:  # noqa: BLE001 - probes convert any client failure into health data
            return DependencyHealth(
                status=DependencyStatus.UNHEALTHY,
                detail=f"Redis probe failed ({type(exc).__name__})",
            )
        if not is_ready:
            return DependencyHealth(
                status=DependencyStatus.UNHEALTHY,
                detail="Redis did not acknowledge the probe",
            )
        return DependencyHealth(status=DependencyStatus.HEALTHY)

    async def close(self) -> None:
        await self._client.aclose()
