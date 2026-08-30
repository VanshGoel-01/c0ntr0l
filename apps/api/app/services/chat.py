import asyncio
import hashlib
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

from control_schemas import (
    ChatCompletion,
    ChatRequest,
    ControlEventType,
    RuntimeDecision,
)

from app.domain.auth import ApiKeyPrincipal
from app.domain.executions import ExecutionTrace
from app.domain.preflight import (
    ModelPolicyAssessment,
    ModelPolicySnapshot,
    evaluate_model_policy,
)
from app.domain.recovery import estimate_chat_input_tokens
from app.domain.streaming import ChatStreamAccumulator
from app.infrastructure.execution_events import ExecutionEvents
from app.providers.errors import (
    ProviderError,
    ProviderResponseError,
    ProviderScenarioUnsupportedError,
)
from app.providers.registry import ProviderRegistry, ProviderSelection
from app.repositories.executions import ExecutionRepository
from app.repositories.model_policies import ModelPolicyRepository


class ChatPolicyBlockedError(Exception):
    def __init__(
        self,
        *,
        execution_id: UUID,
        provider_name: str,
        reason: str,
        checkpoint_id: UUID,
    ) -> None:
        super().__init__(reason)
        self.execution_id = execution_id
        self.provider_name = provider_name
        self.reason = reason
        self.checkpoint_id = checkpoint_id


@dataclass(frozen=True, slots=True)
class ChatResult:
    execution_id: str
    provider_name: str
    decision: RuntimeDecision
    completion: ChatCompletion


@dataclass(frozen=True, slots=True)
class ChatStreamResult:
    execution_id: str
    provider_name: str
    decision: RuntimeDecision
    events: AsyncIterator[str]


class ChatService:
    def __init__(
        self,
        repository: ExecutionRepository,
        providers: ProviderRegistry,
        events: ExecutionEvents | None = None,
        model_policies: ModelPolicyRepository | None = None,
    ) -> None:
        self._repository = repository
        self._providers = providers
        self._events = events
        self._model_policies = model_policies

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
        assessment = await self._admit_with_trace_guard(
            principal,
            trace,
            selection,
            request,
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
            decision=assessment.decision,
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
        await self._publish(
            principal, ControlEventType.EXECUTION_STARTED, trace.execution_id
        )
        assessment = await self._admit_with_trace_guard(
            principal,
            trace,
            selection,
            request,
        )
        provider_stream = selection.provider.stream(request, demo_scenario).__aiter__()
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
            decision=assessment.decision,
            events=relay(),
        )

    async def _admit_with_trace_guard(
        self,
        principal: ApiKeyPrincipal,
        trace: ExecutionTrace,
        selection: ProviderSelection,
        request: ChatRequest,
    ) -> ModelPolicyAssessment:
        started_at = time.perf_counter()
        try:
            return await self._admit(principal, trace, selection, request)
        except ChatPolicyBlockedError:
            raise
        except Exception as admission_error:
            try:
                await self._repository.fail(
                    trace,
                    error_code="admission_control_error",
                    attempt_status="failed",
                    latency_ms=self._elapsed_ms(started_at),
                )
                await self._publish(
                    principal,
                    ControlEventType.EXECUTION_FAILED,
                    trace.execution_id,
                )
            except Exception as trace_error:
                raise admission_error from trace_error
            raise

    async def _admit(
        self,
        principal: ApiKeyPrincipal,
        trace: ExecutionTrace,
        selection: ProviderSelection,
        request: ChatRequest,
    ) -> ModelPolicyAssessment:
        context = None
        if self._model_policies is not None:
            context = await self._model_policies.get(
                principal.project_id,
                selection.name,
                request.model,
            )
        snapshot = (
            ModelPolicySnapshot(
                policy_id=context.id,
                provider=context.provider,
                model=context.model,
                mode=context.mode,
                token_limit=context.token_limit,
            )
            if context is not None
            else None
        )
        assessment = evaluate_model_policy(
            snapshot,
            input_tokens=estimate_chat_input_tokens(request),
            requested_output_tokens=request.max_tokens,
        )
        checkpoint_id = await self._repository.record_model_policy(
            trace,
            request.model,
            assessment,
        )
        if assessment.decision is RuntimeDecision.BLOCK:
            if checkpoint_id is None:
                raise RuntimeError("Blocked chat admission did not create a checkpoint")
            await self._publish(
                principal,
                ControlEventType.EXECUTION_BLOCKED,
                trace.execution_id,
            )
            raise ChatPolicyBlockedError(
                execution_id=trace.execution_id,
                provider_name=selection.name,
                reason=assessment.reason,
                checkpoint_id=checkpoint_id,
            )
        if assessment.projection is not None:
            await self._publish(
                principal,
                ControlEventType.EXECUTION_UPDATED,
                trace.execution_id,
            )
        return assessment

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
