import hashlib
import time

from control_schemas import (
    ChatRequest,
    RuntimeCheckpoint,
    RuntimeRecoveryRequest,
    RuntimeRecoveryResult,
)

from app.domain.recovery import build_recovery_chat_request
from app.providers.errors import ProviderError
from app.providers.registry import ProviderRegistry
from app.repositories.recovery import RecoveryRepository


class RecoveryRunner:
    def __init__(
        self,
        repository: RecoveryRepository,
        providers: ProviderRegistry,
        max_tokens: int,
    ) -> None:
        self._repository = repository
        self._providers = providers
        self._max_tokens = max_tokens

    def build_request(
        self,
        prepared: RuntimeRecoveryResult,
        request: RuntimeRecoveryRequest,
    ) -> ChatRequest:
        model = prepared.target_model
        if model is None:
            raise ValueError("A target model is required for automatic recovery")
        return build_recovery_chat_request(
            packet=prepared.checkpoint.packet,
            target_model=model,
            modified_arguments=request.modified_arguments,
            max_tokens=self._max_tokens,
        )

    async def block(
        self,
        prepared: RuntimeRecoveryResult,
        reason: str,
    ) -> RuntimeRecoveryResult:
        execution_id = prepared.resumed_execution_id
        if execution_id is not None:
            await self._repository.block(execution_id, reason)
        return prepared.model_copy(
            update={
                "status": "blocked",
                "message": f"Recovery was blocked before provider invocation: {reason}",
                "checkpoint": self._available_checkpoint(prepared),
            }
        )

    async def run(
        self,
        prepared: RuntimeRecoveryResult,
        request: RuntimeRecoveryRequest,
        chat_request: ChatRequest | None = None,
    ) -> RuntimeRecoveryResult:
        execution_id = prepared.resumed_execution_id
        provider = prepared.target_provider
        model = prepared.target_model
        if execution_id is None or provider is None or model is None:
            return prepared

        resolved_request = chat_request or self.build_request(prepared, request)
        trace = await self._repository.start(execution_id, provider, model)
        started_at = time.perf_counter()
        try:
            completion = await self._providers.complete(provider, resolved_request)
        except ProviderError as error:
            latency_ms = self._elapsed_ms(started_at)
            await self._repository.fail(
                trace,
                error_code=error.code,
                attempt_status=error.attempt_status,
                latency_ms=latency_ms,
            )
            return prepared.model_copy(
                update={
                    "status": "failed",
                    "message": (
                        f"Recovery could not continue because provider '{provider}' "
                        f"reported {error.code}."
                    ),
                    "checkpoint": self._available_checkpoint(prepared),
                }
            )

        latency_ms = self._elapsed_ms(started_at)
        output_fingerprint = self._fingerprint(completion.model_dump_json())
        await self._repository.complete(
            trace,
            completion,
            provider,
            latency_ms,
            output_fingerprint,
        )
        return prepared.model_copy(
            update={
                "status": "completed",
                "message": (
                    f"Recovery continued through {provider}/{model} and completed."
                ),
                "completion": completion,
            }
        )

    @staticmethod
    def _fingerprint(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return max(0, round((time.perf_counter() - started_at) * 1000))

    @staticmethod
    def _available_checkpoint(prepared: RuntimeRecoveryResult) -> RuntimeCheckpoint:
        return prepared.checkpoint.model_copy(
            update={"status": "available", "consumed_at": None}
        )
