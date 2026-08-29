import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from control_schemas import ChatCompletion
from sqlalchemy import text

from app.domain.recovery import RecoveryTrace
from app.infrastructure.database import Database
from app.repositories.budget_reservations import (
    claim_budget_reservations,
    reconcile_budget_reservations,
)


class RecoveryExecutionNotActiveError(Exception):
    pass


class RecoveryRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def start(
        self,
        execution_id: UUID,
        provider: str,
        model: str,
    ) -> RecoveryTrace:
        async with self._database.begin() as connection:
            execution = (
                await connection.execute(
                    text(
                        """
                        SELECT execution.status, root.id AS root_span_id,
                               COALESCE((
                                   SELECT max(span.sequence_no) + 1
                                   FROM control.spans span
                                   WHERE span.execution_id = execution.id
                               ), 1) AS next_sequence_no
                        FROM control.executions execution
                        JOIN control.spans root
                          ON root.execution_id = execution.id
                         AND root.sequence_no = 1
                        WHERE execution.id = :execution_id
                        FOR UPDATE OF execution
                        """
                    ),
                    {"execution_id": execution_id},
                )
            ).mappings().one_or_none()
            if execution is None or execution["status"] != "running":
                raise RecoveryExecutionNotActiveError

            provider_span_id = UUID(
                str(
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO control.spans (
                                    execution_id, parent_span_id, sequence_no,
                                    kind, name, attributes
                                ) VALUES (
                                    :execution_id, :root_span_id, :sequence_no,
                                    'provider', :name, CAST(:attributes AS jsonb)
                                )
                                RETURNING id
                                """
                            ),
                            {
                                "execution_id": execution_id,
                                "root_span_id": execution["root_span_id"],
                                "sequence_no": execution["next_sequence_no"],
                                "name": f"{provider}.recovery.completion",
                                "attributes": json.dumps(
                                    {"recovery": True, "provider": provider, "model": model}
                                ),
                            },
                        )
                    ).scalar_one()
                )
            )
            provider_attempt_id = UUID(
                str(
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO control.provider_attempts (
                                    execution_id, span_id, attempt_no, provider, model
                                ) VALUES (
                                    :execution_id, :span_id,
                                    COALESCE((SELECT max(attempt_no) + 1
                                              FROM control.provider_attempts
                                              WHERE execution_id = :execution_id), 1),
                                    :provider, :model
                                )
                                RETURNING id
                                """
                            ),
                            {
                                "execution_id": execution_id,
                                "span_id": provider_span_id,
                                "provider": provider,
                                "model": model,
                            },
                        )
                    ).scalar_one()
                )
            )
            await claim_budget_reservations(connection, execution_id)
        return RecoveryTrace(
            execution_id=execution_id,
            root_span_id=UUID(str(execution["root_span_id"])),
            provider_span_id=provider_span_id,
            provider_attempt_id=provider_attempt_id,
        )

    async def complete(
        self,
        trace: RecoveryTrace,
        completion: ChatCompletion,
        provider: str,
        latency_ms: int,
        output_fingerprint: str,
    ) -> None:
        async with self._database.begin() as connection:
            now = await self._database_now(connection)
            await connection.execute(
                text(
                    """
                    UPDATE control.provider_attempts
                    SET status = 'completed', completed_at = :now,
                        retryable = false
                    WHERE id = :attempt_id
                    """
                ),
                {"attempt_id": trace.provider_attempt_id, "now": now},
            )
            await self._finish_span(
                connection, trace.provider_span_id, "completed", latency_ms, now
            )
            await self._finish_span(
                connection, trace.root_span_id, "completed", latency_ms, now
            )
            await connection.execute(
                text(
                    """
                    UPDATE control.executions
                    SET status = 'completed', completed_at = :now,
                        output_fingerprint = :output_fingerprint,
                        final_reason = :final_reason,
                        metadata = metadata || CAST(:metadata AS jsonb)
                    WHERE id = :execution_id
                    """
                ),
                {
                    "execution_id": trace.execution_id,
                    "now": now,
                    "output_fingerprint": output_fingerprint,
                    "final_reason": completion.choices[0].finish_reason,
                    "metadata": json.dumps(
                        {
                            "recovery_state": "completed",
                            "recovery_completion_id": completion.id,
                        }
                    ),
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO control.usage_records (
                        execution_id, span_id, provider_attempt_id, source_type,
                        provider, model, input_tokens, output_tokens,
                        cost_amount, currency, latency_ms
                    ) VALUES (
                        :execution_id, :span_id, :attempt_id, 'provider_reported',
                        :provider, :model, :input_tokens, :output_tokens,
                        0, 'USD', :latency_ms
                    )
                    """
                ),
                {
                    "execution_id": trace.execution_id,
                    "span_id": trace.provider_span_id,
                    "attempt_id": trace.provider_attempt_id,
                    "provider": provider,
                    "model": completion.model,
                    "input_tokens": completion.usage.prompt_tokens,
                    "output_tokens": completion.usage.completion_tokens,
                    "latency_ms": latency_ms,
                },
            )
            await reconcile_budget_reservations(
                connection,
                trace.execution_id,
                actual_tokens=completion.usage.total_tokens,
                actual_cost=Decimal("0"),
                now=now,
            )
            await connection.execute(
                text(
                    """
                    UPDATE control.recovery_attempts
                    SET status = 'completed', completed_at = :now,
                        details = details || CAST(:details AS jsonb)
                    WHERE resumed_execution_id = :execution_id
                      AND status = 'prepared'
                    """
                ),
                {
                    "execution_id": trace.execution_id,
                    "now": now,
                    "details": json.dumps(
                        {
                            "completion_id": completion.id,
                            "total_tokens": completion.usage.total_tokens,
                        }
                    ),
                },
            )
    async def fail(
        self,
        trace: RecoveryTrace,
        *,
        error_code: str,
        attempt_status: str,
        latency_ms: int,
    ) -> None:
        async with self._database.begin() as connection:
            now = await self._database_now(connection)
            await connection.execute(
                text(
                    """
                    UPDATE control.provider_attempts
                    SET status = :status, completed_at = :now,
                        retryable = true, error_category = :error_code
                    WHERE id = :attempt_id
                    """
                ),
                {
                    "attempt_id": trace.provider_attempt_id,
                    "status": attempt_status,
                    "error_code": error_code,
                    "now": now,
                },
            )
            await self._finish_span(
                connection,
                trace.provider_span_id,
                "failed",
                latency_ms,
                now,
                error_code,
            )
            await self._finish_span(
                connection,
                trace.root_span_id,
                "failed",
                latency_ms,
                now,
                error_code,
            )
            await connection.execute(
                text(
                    """
                    UPDATE control.executions
                    SET status = 'failed', completed_at = :now,
                        final_reason = 'recovery_provider_error',
                        error_code = :error_code,
                        metadata = metadata || '{"recovery_state":"failed"}'::jsonb
                    WHERE id = :execution_id
                    """
                ),
                {
                    "execution_id": trace.execution_id,
                    "now": now,
                    "error_code": error_code,
                },
            )
            await connection.execute(
                text(
                    """
                    UPDATE control.recovery_attempts
                    SET status = 'failed', completed_at = :now,
                        details = details || CAST(:details AS jsonb)
                    WHERE resumed_execution_id = :execution_id
                      AND status = 'prepared'
                    """
                ),
                {
                    "execution_id": trace.execution_id,
                    "now": now,
                    "details": json.dumps({"error_code": error_code}),
                },
            )
            await reconcile_budget_reservations(
                connection,
                trace.execution_id,
                actual_tokens=0,
                actual_cost=Decimal("0"),
                now=now,
            )

    @staticmethod
    async def _database_now(connection) -> datetime:  # type: ignore[no-untyped-def]
        return (await connection.execute(text("SELECT clock_timestamp()"))).scalar_one()

    @staticmethod
    async def _finish_span(
        connection,  # type: ignore[no-untyped-def]
        span_id: UUID,
        status: str,
        latency_ms: int,
        now: datetime,
        error_code: str | None = None,
    ) -> None:
        await connection.execute(
            text(
                """
                UPDATE control.spans
                SET status = :status, completed_at = :now,
                    duration_ms = :latency_ms, error_code = :error_code
                WHERE id = :span_id
                """
            ),
            {
                "span_id": span_id,
                "status": status,
                "now": now,
                "latency_ms": latency_ms,
                "error_code": error_code,
            },
        )
