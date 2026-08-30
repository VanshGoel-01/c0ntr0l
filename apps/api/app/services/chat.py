import asyncio
import hashlib
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

from control_schemas import ChatCompletion, ChatRequest, ControlEventType

from app.domain.auth import ApiKeyPrincipal
from app.domain.streaming import ChatStreamAccumulator
from app.infrastructure.execution_events import ExecutionEvents
from app.providers.errors import (
    ProviderError,
    ProviderResponseError,
    ProviderScenarioUnsupportedError,
)
from app.providers.registry import ProviderRegistry, ProviderSelection
from app.repositories.executions import ExecutionRepository


@dataclass(frozen=True, slots=True)
class ChatResult:
    execution_id: str
    provider_name: str
    completion: ChatCompletion


@dataclass(frozen=True, slots=True)
class ChatStreamResult:
    execution_id: str
    provider_name: str
    events: AsyncIterator[str]


class ChatService:
    def __init__(
        self,
        repository: ExecutionRepository,
        providers: ProviderRegistry,
        events: ExecutionEvents | None = None,
    ) -> None:
        self._repository = repository
        self._providers = providers
        self._events = events

    async def complete(
        self,
        principal: ApiKeyPrincipal,
        request: ChatRequest,
        request_id: str | None,
        demo_scenario: str | None,
        requested_provider: str | None = None,
        application_slug: str | None = None,
        agent_slug: str | None = None,
    ) -> ChatResult:
        selection = await self._select_provider(
            request.model, requested_provider, demo_scenario
        )
        resolved_request_id = request_id or f"req_{uuid4().hex}"
        input_fingerprint = self._fingerprint(request.model_dump_json())
        trace = await self._repository.start(
            principal,
            request.model,
            selection.name,
            request.stream,
            resolved_request_id,
            input_fingerprint,
            application_slug,
            agent_slug,
        )
        await self._publish(
            principal, ControlEventType.EXECUTION_STARTED, trace.execution_id
        )
        started_at = time.perf_counter()
        try:
            completion = await selection.provider.complete(request, demo_scenario)
        except ProviderError as exc:
            latency_ms = self._elapsed_ms(started_at)
            await self._repository.fail(
                trace,
                error_code=exc.code,
                attempt_status=exc.attempt_status,
                latency_ms=latency_ms,
            )
            await self._publish(
                principal, ControlEventType.EXECUTION_FAILED, trace.execution_id
            )
            raise

        latency_ms = self._elapsed_ms(started_at)
        await self._repository.complete(
            trace,
            completion,
            latency_ms,
            self._fingerprint(completion.model_dump_json()),
        )
        await self._publish(
            principal, ControlEventType.EXECUTION_COMPLETED, trace.execution_id
        )
        return ChatResult(
            execution_id=str(trace.execution_id),
            provider_name=selection.name,
            completion=completion,
        )

    async def stream(
        self,
        principal: ApiKeyPrincipal,
        request: ChatRequest,
        request_id: str | None,
        demo_scenario: str | None,
        requested_provider: str | None = None,
        application_slug: str | None = None,
        agent_slug: str | None = None,
    ) -> ChatStreamResult:
        selection = await self._select_provider(
            request.model, requested_provider, demo_scenario
        )
        resolved_request_id = request_id or f"req_{uuid4().hex}"
        input_fingerprint = self._fingerprint(request.model_dump_json())
        trace = await self._repository.start(
            principal,
            request.model,
            selection.name,
            True,
            resolved_request_id,
            input_fingerprint,
            application_slug,
            agent_slug,
        )
        provider_stream = selection.provider.stream(request, demo_scenario).__aiter__()
        await self._publish(
            principal, ControlEventType.EXECUTION_STARTED, trace.execution_id
        )
        started_at = time.perf_counter()
        try:
            first_chunk = await anext(provider_stream)
        except StopAsyncIteration as exc:
            error = ProviderResponseError()
            await self._repository.fail(
                trace,
                error_code=error.code,
                attempt_status=error.attempt_status,
                latency_ms=self._elapsed_ms(started_at),
            )
            await self._publish(
                principal, ControlEventType.EXECUTION_FAILED, trace.execution_id
            )
            raise error from exc
        except ProviderError as error:
            await self._repository.fail(
                trace,
                error_code=error.code,
                attempt_status=error.attempt_status,
                latency_ms=self._elapsed_ms(started_at),
            )
            await self._publish(
                principal, ControlEventType.EXECUTION_FAILED, trace.execution_id
            )
            raise

        async def relay() -> AsyncIterator[str]:
            accumulator = ChatStreamAccumulator()
            try:
                accumulator.add(first_chunk)
                yield self._stream_event(first_chunk.model_dump_json(exclude_none=True))
                async for chunk in provider_stream:
                    accumulator.add(chunk)
                    yield self._stream_event(chunk.model_dump_json(exclude_none=True))

                completion = accumulator.completion()
                latency_ms = self._elapsed_ms(started_at)
                await self._repository.complete(
                    trace,
                    completion,
                    latency_ms,
                    self._fingerprint(completion.model_dump_json()),
                )
                await self._publish(
                    principal,
                    ControlEventType.EXECUTION_COMPLETED,
                    trace.execution_id,
                )
                yield "data: [DONE]\n\n"
            except ProviderError as error:
                await self._repository.fail(
                    trace,
                    error_code=error.code,
                    attempt_status=error.attempt_status,
                    latency_ms=self._elapsed_ms(started_at),
                )
                await self._publish(
                    principal, ControlEventType.EXECUTION_FAILED, trace.execution_id
                )
                raise
            except asyncio.CancelledError:
                await self._repository.fail(
                    trace,
                    error_code="client_disconnected",
                    attempt_status="failed",
                    latency_ms=self._elapsed_ms(started_at),
                )
                await self._publish(
                    principal, ControlEventType.EXECUTION_FAILED, trace.execution_id
                )
                raise
            finally:
                await provider_stream.aclose()

        return ChatStreamResult(
            execution_id=str(trace.execution_id),
            provider_name=selection.name,
            events=relay(),
        )

    async def _select_provider(
        self,
        model: str,
        requested_provider: str | None,
        demo_scenario: str | None,
    ) -> ProviderSelection:
        selection = await self._providers.select(model, requested_provider)
        if demo_scenario is not None and selection.name != "mock":
            raise ProviderScenarioUnsupportedError
        return selection

    @staticmethod
    def _fingerprint(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return max(0, round((time.perf_counter() - started_at) * 1000))

    @staticmethod
    def _stream_event(payload: str) -> str:
        return f"data: {payload}\n\n"

    async def _publish(
        self,
        principal: ApiKeyPrincipal,
        event_type: ControlEventType,
        execution_id: UUID,
    ) -> None:
        if self._events is not None:
            await self._events.publish(
                principal.project_id,
                event_type,
                execution_id,
            )
