from datetime import UTC, datetime
from uuid import UUID

import pytest
from app.infrastructure.execution_events import ExecutionEvents
from control_schemas import ControlEventType

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
EXECUTION_ID = UUID("00000000-0000-0000-0000-000000000002")


class FakeRedis:
    def __init__(self) -> None:
        self.added = None
        self.reads = 0

    async def xadd(self, key, fields, **kwargs):  # type: ignore[no-untyped-def]
        self.added = (key, fields, kwargs)
        return "10-0"

    async def xrevrange(self, key, count):  # type: ignore[no-untyped-def]
        return [("9-0", {})]

    async def xread(self, streams, **kwargs):  # type: ignore[no-untyped-def]
        self.reads += 1
        return [
            (
                next(iter(streams)),
                [
                    (
                        "10-0",
                        {
                            "type": "execution.completed",
                            "execution_id": str(EXECUTION_ID),
                            "occurred_at": datetime.now(UTC).isoformat(),
                        },
                    )
                ],
            )
        ]

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_events_are_project_scoped_and_resumable() -> None:
    redis = FakeRedis()
    events = ExecutionEvents(
        "redis://unused",
        max_events=500,
        client=redis,  # type: ignore[arg-type]
    )

    published = await events.publish(
        PROJECT_ID,
        ControlEventType.EXECUTION_COMPLETED,
        EXECUTION_ID,
    )
    event = await anext(events.subscribe(PROJECT_ID, None))

    assert published is True
    assert redis.added[0] == f"control:project:{PROJECT_ID}:events"
    assert redis.added[2] == {"maxlen": 500, "approximate": True}
    assert event.id == "10-0"
    assert event.execution_id == EXECUTION_ID
    assert event.type is ControlEventType.EXECUTION_COMPLETED


@pytest.mark.asyncio
async def test_explicit_last_event_id_is_used_as_cursor() -> None:
    redis = FakeRedis()
    events = ExecutionEvents("redis://unused", client=redis)  # type: ignore[arg-type]
    subscription = events.subscribe(PROJECT_ID, "8-4")

    await anext(subscription)

    assert redis.reads == 1
