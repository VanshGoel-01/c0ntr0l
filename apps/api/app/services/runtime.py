from uuid import UUID

from control_schemas import (
    ControlEventType,
    RecoveryStrategy,
    RuntimeActionCheckRequest,
    RuntimeActionCompleted,
    RuntimeActionCompleteRequest,
    RuntimeActionDecision,
    RuntimeCancellationResult,
    RuntimeDecision,
    RuntimeExecutionCreated,
    RuntimeExecutionRequest,
    RuntimeIntervention,
    RuntimePreflightRequest,
    RuntimePreflightResult,
    RuntimeRecoveryRequest,
    RuntimeRecoveryResult,
)

from app.domain.auth import ApiKeyPrincipal
from app.domain.recovery import estimate_chat_input_tokens
from app.infrastructure.execution_events import ExecutionEvents
from app.infrastructure.runtime_signals import RuntimeSignals
from app.providers.registry import ProviderRegistry
from app.repositories.runtime import RuntimeRepository
from app.services.recovery import RecoveryRunner


class RuntimeService:
    def __init__(
        self,
        repository: RuntimeRepository,
        signals: RuntimeSignals,
        recovery_runner: RecoveryRunner,
        providers: ProviderRegistry,
        default_context_window_tokens: int,
        context_safety_margin_tokens: int,
        context_warning_utilization: float,
        events: ExecutionEvents | None = None,
    ) -> None:
        self._repository = repository
        self._signals = signals
        self._recovery_runner = recovery_runner
        self._providers = providers
        self._default_context_window_tokens = default_context_window_tokens
        self._context_safety_margin_tokens = context_safety_margin_tokens
        self._context_warning_utilization = context_warning_utilization
        self._events = events

    async def start(
        self,
        principal: ApiKeyPrincipal,
        request: RuntimeExecutionRequest,
    ) -> RuntimeExecutionCreated:
        result = await self._repository.start(principal, request)
        await self._publish(
            principal,
            ControlEventType.EXECUTION_STARTED,
            result.execution_id,
        )
        return result

    async def check_action(
        self,
        principal: ApiKeyPrincipal,
        execution_id: UUID,
        request: RuntimeActionCheckRequest,
    ) -> RuntimeActionDecision:
        if await self._signals.is_cancellation_requested(
            principal.project_id, execution_id
        ):
            await self._repository.cancel(principal, execution_id)
        result = await self._repository.check_action(principal, execution_id, request)
        await self._publish(
            principal,
            (
                ControlEventType.EXECUTION_BLOCKED
                if result.decision is RuntimeDecision.BLOCK
                else ControlEventType.EXECUTION_UPDATED
            ),
            execution_id,
        )
        return result

    async def preflight(
        self,
        principal: ApiKeyPrincipal,
        execution_id: UUID,
        request: RuntimePreflightRequest,
    ) -> RuntimePreflightResult:
        execution = await self._repository.get_preflight_execution(
            principal, execution_id
        )
        context_window = await self._providers.context_window(
            execution.provider,
            execution.model,
            self._default_context_window_tokens,
        )
        result = await self._repository.record_preflight(
            principal,
            execution,
            request,
            context_window_tokens=context_window,
            safety_margin_tokens=self._context_safety_margin_tokens,
            warning_utilization=self._context_warning_utilization,
        )
        await self._publish(
            principal,
            (
                ControlEventType.EXECUTION_BLOCKED
                if result.decision is RuntimeDecision.BLOCK
                else ControlEventType.EXECUTION_UPDATED
            ),
            execution_id,
        )
        return result

    async def complete_action(
        self,
        principal: ApiKeyPrincipal,
        execution_id: UUID,
        action_id: UUID,
        request: RuntimeActionCompleteRequest,
    ) -> RuntimeActionCompleted:
        result = await self._repository.complete_action(
            principal, execution_id, action_id, request
        )
        await self._publish(
            principal,
            ControlEventType.EXECUTION_UPDATED,
            execution_id,
        )
        return result

    async def get_intervention(
        self,
        principal: ApiKeyPrincipal,
        execution_id: UUID,
    ) -> RuntimeIntervention | None:
        return await self._repository.get_intervention(principal, execution_id)

    async def cancel(
        self,
        principal: ApiKeyPrincipal,
        execution_id: UUID,
    ) -> RuntimeCancellationResult:
        await self._repository.authorize_execution(principal, execution_id)
        await self._signals.request_cancellation(principal.project_id, execution_id)
        try:
            result = await self._repository.cancel(principal, execution_id)
            await self._publish(
                principal,
                ControlEventType.EXECUTION_CANCELLED,
                execution_id,
            )
            return result
        except Exception:
            await self._signals.clear_cancellation(principal.project_id, execution_id)
            raise

    async def recover(
        self,
        principal: ApiKeyPrincipal,
        execution_id: UUID,
        request: RuntimeRecoveryRequest,
    ) -> RuntimeRecoveryResult:
        result = await self._repository.recover(principal, execution_id, request)
        if result.resumed_execution_id is not None:
            await self._signals.clear_cancellation(
                principal.project_id, result.resumed_execution_id
            )
        if request.strategy in {
            RecoveryStrategy.RETRY_MODIFIED,
            RecoveryStrategy.MODEL_HANDOFF,
        }:
            if result.resumed_execution_id is None:
                await self._publish_recovery(principal, result)
                return result
            chat_request = self._recovery_runner.build_request(result, request)
            admission = await self.preflight(
                principal,
                result.resumed_execution_id,
                RuntimePreflightRequest(
                    input_tokens=estimate_chat_input_tokens(chat_request),
                    requested_output_tokens=chat_request.max_tokens,
                ),
            )
            if admission.decision is RuntimeDecision.BLOCK:
                blocked = await self._recovery_runner.block(result, admission.reason)
                await self._publish_recovery(principal, blocked)
                return blocked
            recovered = await self._recovery_runner.run(
                result,
                request,
                chat_request,
            )
            await self._publish_recovery(principal, recovered)
            return recovered
        await self._publish_recovery(principal, result)
        return result

    async def _publish_recovery(
        self,
        principal: ApiKeyPrincipal,
        result: RuntimeRecoveryResult,
    ) -> None:
        await self._publish(
            principal,
            ControlEventType.RECOVERY_UPDATED,
            result.source_execution_id,
        )
        if result.resumed_execution_id is not None:
            event_type = {
                "blocked": ControlEventType.EXECUTION_BLOCKED,
                "completed": ControlEventType.EXECUTION_COMPLETED,
                "failed": ControlEventType.EXECUTION_FAILED,
            }.get(result.status, ControlEventType.EXECUTION_UPDATED)
            await self._publish(
                principal,
                event_type,
                result.resumed_execution_id,
            )

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
