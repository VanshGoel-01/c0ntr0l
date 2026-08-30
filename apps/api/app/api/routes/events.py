from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_execution_events, get_principal
from app.domain.auth import ApiKeyPrincipal
from app.infrastructure.execution_events import ExecutionEvents

router = APIRouter(prefix="/api/v1/events", tags=["events"])
PrincipalDependency = Annotated[ApiKeyPrincipal, Depends(get_principal)]
EventsDependency = Annotated[ExecutionEvents, Depends(get_execution_events)]
LastEventIdHeader = Annotated[
    str | None,
    Header(alias="Last-Event-ID", pattern=r"^\d+-\d+$", max_length=64),
]


@router.get("", operation_id="streamControlEvents")
async def stream_control_events(
    request: Request,
    principal: PrincipalDependency,
    events: EventsDependency,
    last_event_id: LastEventIdHeader = None,
) -> StreamingResponse:
    async def relay() -> AsyncIterator[str]:
        async for event in events.subscribe(principal.project_id, last_event_id):
            if await request.is_disconnected():
                return
            if event is None:
                yield ": keep-alive\n\n"
                continue
            yield (
                f"id: {event.id}\n"
                f"event: {event.type.value}\n"
                f"data: {event.model_dump_json()}\n\n"
            )

    return StreamingResponse(
        relay(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )
