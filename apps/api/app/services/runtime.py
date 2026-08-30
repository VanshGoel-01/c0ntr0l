from uuid import UUID

from control_schemas import (
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
    ) -> None:
        self._repository = repository
        self._signals = signals
        self._recovery_runner = recovery_runner
        self._providers = providers
        self._default_context_window_tokens = default_context_window_tokens
        self._context_safety_margin_tokens = context_safety_margin_tokens
        self._context_warning_utilization = context_warning_utilization

    async def start(
        self,
        principal: ApiKeyPrincipal,
        request: RuntimeExecutionRequest,
    ) -> RuntimeExecutionCreated:
        return await self._repository.start(principal, request)

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
        return await self._repository.check_action(principal, execution_id, request)

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
        return await self._repository.record_preflight(
            principal,
            execution,
            request,
            context_window_tokens=context_window,
            safety_margin_tokens=self._context_safety_margin_tokens,
            warning_utilization=self._context_warning_utilization,
        )

    async def complete_action(
        self,
        principal: ApiKeyPrincipal,
        execution_id: UUID,
        action_id: UUID,
        request: RuntimeActionCompleteRequest,
    ) -> RuntimeActionCompleted:
        return await self._repository.complete_action(
            principal, execution_id, action_id, request
        )

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
            return await self._repository.cancel(principal, execution_id)
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
                return await self._recovery_runner.block(result, admission.reason)
            return await self._recovery_runner.run(
                result,
                request,
                chat_request,
            )
        return result
