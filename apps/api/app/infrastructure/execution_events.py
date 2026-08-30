from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

from control_schemas import ControlEvent, ControlEventType
from redis.asyncio import Redis
from redis.exceptions import RedisError


class ExecutionEvents:
    def __init__(
        self,
        redis_url: str,
        *,
        max_events: int = 1_000,
        block_milliseconds: int = 15_000,
        client: Redis | None = None,
    ) -> None:
        self._client = client or Redis.from_url(redis_url, decode_responses=True)
        self._max_events = max_events
        self._block_milliseconds = block_milliseconds

    async def publish(
        self,
        project_id: UUID,
        event_type: ControlEventType,
        execution_id: UUID | None = None,
    ) -> bool:
        fields = {
            "type": event_type.value,
            "execution_id": str(execution_id) if execution_id else "",
            "occurred_at": datetime.now(UTC).isoformat(),
        }
        try:
            await self._client.xadd(
                self._stream_key(project_id),
                fields,
                maxlen=self._max_events,
                approximate=True,
            )
        except RedisError:
            return False
        return True

    async def subscribe(
        self,
        project_id: UUID,
        last_event_id: str | None,
    ) -> AsyncIterator[ControlEvent | None]:
        key = self._stream_key(project_id)
        cursor = last_event_id or await self._latest_id(key)
        while True:
            rows = await self._client.xread(
                {key: cursor},
                count=100,
                block=self._block_milliseconds,
            )
            if not rows:
                yield None
                continue
            for _, events in rows:
                for event_id, fields in events:
                    cursor = event_id
                    yield ControlEvent(
                        id=event_id,
                        type=ControlEventType(fields["type"]),
                        execution_id=(
                            UUID(fields["execution_id"])
                            if fields.get("execution_id")
                            else None
                        ),
                        occurred_at=datetime.fromisoformat(fields["occurred_at"]),
                    )

    async def close(self) -> None:
        await self._client.aclose()

    async def _latest_id(self, key: str) -> str:
        rows = await self._client.xrevrange(key, count=1)
        return rows[0][0] if rows else "0-0"

    @staticmethod
    def _stream_key(project_id: UUID) -> str:
        return f"control:project:{project_id}:events"
