from uuid import UUID

from redis.asyncio import Redis


class RuntimeSignals:
    def __init__(self, redis_url: str, ttl_seconds: int = 86_400) -> None:
        self._client = Redis.from_url(redis_url, decode_responses=True)
        self._ttl_seconds = ttl_seconds

    async def request_cancellation(
        self, project_id: UUID, execution_id: UUID
    ) -> None:
        await self._client.set(
            self._cancel_key(project_id, execution_id),
            "1",
            ex=self._ttl_seconds,
        )

    async def is_cancellation_requested(
        self, project_id: UUID, execution_id: UUID
    ) -> bool:
        return await self._client.exists(self._cancel_key(project_id, execution_id)) > 0

    async def clear_cancellation(
        self, project_id: UUID, execution_id: UUID
    ) -> None:
        await self._client.delete(self._cancel_key(project_id, execution_id))

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _cancel_key(project_id: UUID, execution_id: UUID) -> str:
        return (
            f"control:project:{project_id}:execution:{execution_id}:cancel_requested"
        )
