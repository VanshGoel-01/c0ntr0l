from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import Any, Literal, TypeVar, cast
from uuid import UUID

from control_schemas import (
    RecoveryStrategy,
    RuntimeActionCheckRequest,
    RuntimeActionCompleteRequest,
    RuntimeDecision,
    RuntimeExecutionCreated,
    RuntimeExecutionRequest,
    RuntimeIntervention,
    RuntimePreflightRequest,
    RuntimeRecoveryResult,
)

from control_sdk.client import ControlRuntimeClient
from control_sdk.errors import ActionBlockedError, ModelPreflightBlockedError

Result = TypeVar("Result")
ProgressEvaluator = bool | Callable[[Result], bool]
SummaryFactory = str | Callable[[Result], str | None] | None
ResultSerializer = Callable[[Result], Any]


class ControlledExecution:
    def __init__(
        self,
        client: ControlRuntimeClient,
        execution: RuntimeExecutionCreated,
    ) -> None:
        self.client = client
        self.execution = execution

    @classmethod
    async def start(
        cls,
        client: ControlRuntimeClient,
        request: RuntimeExecutionRequest,
    ) -> "ControlledExecution":
        execution = await client.start_execution(request)
        return cls(client, execution)

    @property
    def execution_id(self) -> UUID:
        return self.execution.execution_id

    async def run_tool(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        handler: Callable[[], Result | Awaitable[Result]],
        progress: ProgressEvaluator[Result],
        summary: SummaryFactory[Result] = None,
        serialize_result: ResultSerializer[Result] | None = None,
    ) -> Result:
        return await self._run_action(
            kind="tool",
            name=name,
            arguments=arguments,
            handler=handler,
            progress=progress,
            summary=summary,
            serialize_result=serialize_result,
        )

    async def run_model(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        handler: Callable[[], Result | Awaitable[Result]],
        progress: ProgressEvaluator[Result],
        summary: SummaryFactory[Result] = None,
        serialize_result: ResultSerializer[Result] | None = None,
        preflight: RuntimePreflightRequest | None = None,
    ) -> Result:
        if preflight is not None:
            preflight_result = await self.client.preflight_model_call(
                self.execution_id, preflight
            )
            if preflight_result.decision is RuntimeDecision.BLOCK:
                raise ModelPreflightBlockedError(preflight_result)
        return await self._run_action(
            kind="model",
            name=name,
            arguments=arguments,
            handler=handler,
            progress=progress,
            summary=summary,
            serialize_result=serialize_result,
        )

    async def intervention(self) -> RuntimeIntervention:
        return await self.client.get_intervention(self.execution_id)

    async def recover(
        self,
        *,
        strategy: RecoveryStrategy,
        target_provider: str | None = None,
        target_model: str | None = None,
        modified_arguments: dict[str, Any] | None = None,
    ) -> RuntimeRecoveryResult:
        return await self.client.recover_execution(
            self.execution_id,
            strategy=strategy,
            target_provider=target_provider,
            target_model=target_model,
            modified_arguments=modified_arguments,
        )

    async def _run_action(
        self,
        *,
        kind: Literal["tool", "model"],
        name: str,
        arguments: dict[str, Any],
        handler: Callable[[], Result | Awaitable[Result]],
        progress: ProgressEvaluator[Result],
        summary: SummaryFactory[Result],
        serialize_result: ResultSerializer[Result] | None,
    ) -> Result:
        decision = await self.client.check_action(
            self.execution_id,
            RuntimeActionCheckRequest(kind=kind, name=name, arguments=arguments),
        )
        if decision.decision in {RuntimeDecision.BLOCK, RuntimeDecision.CANCEL}:
            raise ActionBlockedError(decision)

        try:
            pending_result = handler()
            result = (
                await cast(Awaitable[Result], pending_result)
                if isawaitable(pending_result)
                else cast(Result, pending_result)
            )
        except Exception as exc:
            await self._report_failure(decision.action_id, exc)
            raise

        made_progress = progress(result) if callable(progress) else progress
        action_summary = summary(result) if callable(summary) else summary
        reported_result = (
            serialize_result(result) if serialize_result is not None else result
        )
        await self.client.complete_action(
            self.execution_id,
            decision.action_id,
            RuntimeActionCompleteRequest(
                status="completed",
                result=reported_result,
                progress=made_progress,
                summary=action_summary,
            ),
        )
        return result

    async def _report_failure(self, action_id: UUID, error: Exception) -> None:
        try:
            await self.client.complete_action(
                self.execution_id,
                action_id,
                RuntimeActionCompleteRequest(
                    status="failed",
                    result={"error_type": type(error).__name__},
                    progress=False,
                    summary=f"{type(error).__name__} raised by guarded action",
                ),
            )
        except Exception as report_error:
            error.add_note(
                "c0ntr0l could not record the failed action: "
                f"{type(report_error).__name__}"
            )
