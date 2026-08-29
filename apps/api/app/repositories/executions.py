from datetime import UTC, datetime
from uuid import UUID

from control_schemas import (
    ChatCompletion,
    ExecutionDetail,
    ExecutionSummary,
    SpanSummary,
    UsageSummary,
)
from sqlalchemy import text

from app.domain.auth import ApiKeyPrincipal
from app.domain.executions import ExecutionTrace
from app.infrastructure.database import Database

_EXECUTION_SUMMARY_SELECT = """
    SELECT
        execution.id,
        execution.request_id,
        execution.project_id,
        project.name AS project_name,
        execution.application_id,
        application.name AS application_name,
        execution.agent_id,
        agent.name AS agent_name,
        execution.status,
        execution.requested_model,
        execution.active_provider,
        execution.active_model,
        execution.is_streaming,
        execution.input_fingerprint,
        execution.output_fingerprint,
        execution.final_reason,
        execution.error_code,
        execution.started_at,
        execution.completed_at,
        CASE
            WHEN execution.completed_at IS NULL THEN NULL
            ELSE GREATEST(
                0,
                round(extract(epoch FROM (
                    execution.completed_at - execution.started_at
                )) * 1000)::bigint
            )
        END AS duration_ms,
        (SELECT count(*) FROM control.spans span
         WHERE span.execution_id = execution.id) AS span_count,
        COALESCE((SELECT sum(usage.total_tokens)
                  FROM control.usage_records usage
                  WHERE usage.execution_id = execution.id), 0) AS total_tokens,
        COALESCE((SELECT sum(usage.cost_amount)
                  FROM control.usage_records usage
                  WHERE usage.execution_id = execution.id), 0) AS total_cost
        , execution.metadata
    FROM control.executions execution
    JOIN control.projects project ON project.id = execution.project_id
    LEFT JOIN control.applications application ON application.id = execution.application_id
    LEFT JOIN control.agents agent ON agent.id = execution.agent_id
"""

_RECENT_EXECUTIONS_QUERY = text(
    _EXECUTION_SUMMARY_SELECT
    + """
    WHERE execution.project_id = :project_id
    ORDER BY execution.started_at DESC
    LIMIT :limit
    """
)

_EXECUTION_DETAIL_QUERY = text(
    _EXECUTION_SUMMARY_SELECT
    + """
    WHERE execution.project_id = :project_id
      AND execution.id = :execution_id
    """
)


class ExecutionRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def start(
        self,
        principal: ApiKeyPrincipal,
        requested_model: str,
        is_streaming: bool,
        request_id: str,
        input_fingerprint: str,
        application_slug: str | None = None,
        agent_slug: str | None = None,
    ) -> ExecutionTrace:
        async with self._database.begin() as connection:
            execution_id = UUID(
                str(
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO control.executions (
                                    request_id, organization_id, project_id,
                                    application_id, agent_id, status,
                                    requested_model, active_provider, active_model,
                                    is_streaming, input_fingerprint
                                ) VALUES (
                                    :request_id, :organization_id, :project_id,
                                    (SELECT id FROM control.applications
                                     WHERE project_id = :project_id
                                       AND slug = :application_slug
                                       AND status = 'active'),
                                    (SELECT agent.id FROM control.agents agent
                                     JOIN control.applications application
                                       ON application.id = agent.application_id
                                     WHERE application.project_id = :project_id
                                       AND application.slug = :application_slug
                                       AND agent.slug = :agent_slug
                                       AND agent.status = 'active'),
                                    'running',
                                    :model, 'mock', :model, :is_streaming, :input_fingerprint
                                )
                                RETURNING id
                                """
                            ),
                            {
                                "request_id": request_id,
                                "organization_id": principal.organization_id,
                                "project_id": principal.project_id,
                                "model": requested_model,
                                "is_streaming": is_streaming,
                                "input_fingerprint": input_fingerprint,
                                "application_slug": application_slug,
                                "agent_slug": agent_slug,
                            },
                        )
                    ).scalar_one()
                )
            )
            root_span_id = await self._insert_span(
                connection,
                execution_id=execution_id,
                sequence_no=1,
                kind="gateway",
                name="chat.completion",
            )
            provider_span_id = await self._insert_span(
                connection,
                execution_id=execution_id,
                sequence_no=2,
                kind="provider",
                name="mock.chat.completion",
                parent_span_id=root_span_id,
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
                                    :execution_id, :span_id, 1, 'mock', :model
                                )
                                RETURNING id
                                """
                            ),
                            {
                                "execution_id": execution_id,
                                "span_id": provider_span_id,
                                "model": requested_model,
                            },
                        )
                    ).scalar_one()
                )
            )
        return ExecutionTrace(
            execution_id=execution_id,
            root_span_id=root_span_id,
            provider_span_id=provider_span_id,
            provider_attempt_id=provider_attempt_id,
        )

    async def complete(
        self,
        trace: ExecutionTrace,
        completion: ChatCompletion,
        latency_ms: int,
        output_fingerprint: str,
    ) -> None:
        now = datetime.now(UTC)
        async with self._database.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE control.provider_attempts
                    SET status = 'completed', completed_at = :completed_at, retryable = false
                    WHERE id = :attempt_id
                    """
                ),
                {"attempt_id": trace.provider_attempt_id, "completed_at": now},
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
                    SET status = 'completed', completed_at = :completed_at,
                        output_fingerprint = :output_fingerprint, final_reason = :final_reason
                    WHERE id = :execution_id
                    """
                ),
                {
                    "execution_id": trace.execution_id,
                    "completed_at": now,
                    "output_fingerprint": output_fingerprint,
                    "final_reason": completion.choices[0].finish_reason,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO control.usage_records (
                        execution_id, span_id, provider_attempt_id, source_type,
                        provider, model, input_tokens, output_tokens, cost_amount,
                        currency, latency_ms
                    ) VALUES (
                        :execution_id, :span_id, :attempt_id, 'provider_reported',
                        'mock', :model, :input_tokens, :output_tokens, 0,
                        'USD', :latency_ms
                    )
                    """
                ),
                {
                    "execution_id": trace.execution_id,
                    "span_id": trace.provider_span_id,
                    "attempt_id": trace.provider_attempt_id,
                    "model": completion.model,
                    "input_tokens": completion.usage.prompt_tokens,
                    "output_tokens": completion.usage.completion_tokens,
                    "latency_ms": latency_ms,
                },
            )

    async def fail(
        self,
        trace: ExecutionTrace,
        error_code: str,
        attempt_status: str,
        latency_ms: int,
    ) -> None:
        now = datetime.now(UTC)
        async with self._database.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE control.provider_attempts
                    SET status = :status, completed_at = :completed_at,
                        retryable = true, error_category = :error_code
                    WHERE id = :attempt_id
                    """
                ),
                {
                    "attempt_id": trace.provider_attempt_id,
                    "status": attempt_status,
                    "completed_at": now,
                    "error_code": error_code,
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
                    SET status = 'failed', completed_at = :completed_at,
                        final_reason = 'provider_error', error_code = :error_code
                    WHERE id = :execution_id
                    """
                ),
                {
                    "execution_id": trace.execution_id,
                    "completed_at": now,
                    "error_code": error_code,
                },
            )

    async def list_recent(self, project_id: UUID, limit: int) -> list[ExecutionSummary]:
        async with self._database.connect() as connection:
            rows = (
                await connection.execute(
                    _RECENT_EXECUTIONS_QUERY,
                    {"project_id": project_id, "limit": limit},
                )
            ).mappings()
        return [ExecutionSummary.model_validate(dict(row)) for row in rows]

    async def get(
        self,
        project_id: UUID,
        execution_id: UUID,
    ) -> ExecutionDetail | None:
        async with self._database.connect() as connection:
            summary_row = (
                (
                    await connection.execute(
                        _EXECUTION_DETAIL_QUERY,
                        {"project_id": project_id, "execution_id": execution_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if summary_row is None:
                return None
            span_rows = (
                await connection.execute(
                    text(
                        """
                        SELECT id, parent_span_id, sequence_no, kind, name, tool_name,
                               status, duration_ms, error_code, started_at, completed_at,
                               attributes
                        FROM control.spans
                        WHERE execution_id = :execution_id
                        ORDER BY sequence_no
                        """
                    ),
                    {"execution_id": execution_id},
                )
            ).mappings()
            usage_rows = (
                await connection.execute(
                    text(
                        """
                        SELECT source_type, provider, model, input_tokens, output_tokens,
                               total_tokens, cost_amount, currency, latency_ms, observed_at
                        FROM control.usage_records
                        WHERE execution_id = :execution_id
                        ORDER BY observed_at
                        """
                    ),
                    {"execution_id": execution_id},
                )
            ).mappings()

        summary = ExecutionSummary.model_validate(dict(summary_row))
        return ExecutionDetail(
            **summary.model_dump(),
            spans=[SpanSummary.model_validate(dict(row)) for row in span_rows],
            usage=[UsageSummary.model_validate(dict(row)) for row in usage_rows],
        )

    @staticmethod
    async def _insert_span(
        connection,  # type: ignore[no-untyped-def]
        execution_id: UUID,
        sequence_no: int,
        kind: str,
        name: str,
        parent_span_id: UUID | None = None,
    ) -> UUID:
        value = (
            await connection.execute(
                text(
                    """
                    INSERT INTO control.spans (
                        execution_id, parent_span_id, sequence_no, kind, name
                    ) VALUES (
                        :execution_id, :parent_span_id, :sequence_no, :kind, :name
                    )
                    RETURNING id
                    """
                ),
                {
                    "execution_id": execution_id,
                    "parent_span_id": parent_span_id,
                    "sequence_no": sequence_no,
                    "kind": kind,
                    "name": name,
                },
            )
        ).scalar_one()
        return UUID(str(value))

    @staticmethod
    async def _finish_span(
        connection,  # type: ignore[no-untyped-def]
        span_id: UUID,
        span_status: str,
        duration_ms: int,
        completed_at: datetime,
        error_code: str | None = None,
    ) -> None:
        await connection.execute(
            text(
                """
                UPDATE control.spans
                SET status = :status, completed_at = :completed_at,
                    duration_ms = :duration_ms, error_code = :error_code
                WHERE id = :span_id
                """
            ),
            {
                "span_id": span_id,
                "status": span_status,
                "completed_at": completed_at,
                "duration_ms": duration_ms,
                "error_code": error_code,
            },
        )
