import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from control_schemas import (
    ChatCompletion,
    ExecutionDetail,
    ExecutionSummary,
    RuntimeDecision,
    SpanSummary,
    UsageSummary,
)
from sqlalchemy import text

from app.domain.auth import ApiKeyPrincipal
from app.domain.executions import ExecutionTrace
from app.domain.preflight import ModelPolicyAssessment
from app.infrastructure.database import Database
from app.repositories.budget_reservations import (
    claim_budget_reservations,
    reconcile_budget_reservations,
)

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
        provider_name: str,
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
                                    :model, :provider, :model, :is_streaming, :input_fingerprint
                                )
                                RETURNING id
                                """
                            ),
                            {
                                "request_id": request_id,
                                "organization_id": principal.organization_id,
                                "project_id": principal.project_id,
                                "model": requested_model,
                                "provider": provider_name,
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
                name=f"{provider_name}.chat.completion",
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
                                    :execution_id, :span_id, 1, :provider, :model
                                )
                                RETURNING id
                                """
                            ),
                            {
                                "execution_id": execution_id,
                                "span_id": provider_span_id,
                                "model": requested_model,
                                "provider": provider_name,
                            },
                        )
                    ).scalar_one()
                )
            )
            await claim_budget_reservations(connection, execution_id)
        return ExecutionTrace(
            execution_id=execution_id,
            root_span_id=root_span_id,
            provider_span_id=provider_span_id,
            provider_attempt_id=provider_attempt_id,
            provider_name=provider_name,
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
                        :provider, :model, :input_tokens, :output_tokens, 0,
                        'USD', :latency_ms
                    )
                    """
                ),
                {
                    "execution_id": trace.execution_id,
                    "span_id": trace.provider_span_id,
                    "attempt_id": trace.provider_attempt_id,
                    "model": completion.model,
                    "provider": trace.provider_name,
                    "input_tokens": completion.usage.prompt_tokens,
                    "output_tokens": completion.usage.completion_tokens,
                    "latency_ms": latency_ms,
                },
            )
            await reconcile_budget_reservations(
                connection,
                trace.execution_id,
                actual_tokens=completion.usage.total_tokens,
                actual_cost=Decimal(0),
                now=now,
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
            await reconcile_budget_reservations(
                connection,
                trace.execution_id,
                actual_tokens=0,
                actual_cost=Decimal(0),
                now=now,
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

    async def record_model_policy(
        self,
        trace: ExecutionTrace,
        model: str,
        assessment: ModelPolicyAssessment,
    ) -> UUID | None:
        projection = assessment.projection
        if projection is None:
            return None
        blocked = assessment.decision is RuntimeDecision.BLOCK
        warned = assessment.decision is RuntimeDecision.WARN
        evidence = {
            "reason": assessment.reason,
            "provider": trace.provider_name,
            "model": model,
            **projection.model_dump(mode="json"),
        }
        async with self._database.begin() as connection:
            policy_span_id = await self._insert_span(
                connection,
                execution_id=trace.execution_id,
                sequence_no=3,
                kind="policy",
                name="Chat model policy admission",
                parent_span_id=trace.root_span_id,
            )
            now = datetime.now(UTC)
            await self._finish_span(
                connection,
                policy_span_id,
                "blocked" if blocked else "completed",
                0,
                now,
                "model_policy_block" if blocked else None,
            )
            decision_id = UUID(
                str(
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO control.policy_decisions (
                                    execution_id, triggering_span_id,
                                    model_policy_id, policy_code, policy_version,
                                    mode, outcome, final_execution_state, evidence
                                ) VALUES (
                                    :execution_id, :span_id, :model_policy_id,
                                    'chat_model_policy', '1.0', :mode, :outcome,
                                    :final_state, CAST(:evidence AS jsonb)
                                )
                                RETURNING id
                                """
                            ),
                            {
                                "execution_id": trace.execution_id,
                                "span_id": policy_span_id,
                                "model_policy_id": projection.policy_id,
                                "mode": assessment.mode.value,
                                "outcome": assessment.decision.value,
                                "final_state": "blocked" if blocked else "running",
                                "evidence": json.dumps(evidence),
                            },
                        )
                    ).scalar_one()
                )
            )
            if warned:
                await self._insert_model_policy_incident(
                    connection,
                    trace.execution_id,
                    decision_id,
                    policy_span_id,
                    "warning",
                    "Model policy warning",
                    evidence,
                )
            if not blocked:
                return None

            await connection.execute(
                text(
                    """
                    UPDATE control.provider_attempts
                    SET status = 'skipped', completed_at = :completed_at,
                        retryable = false, error_category = 'model_policy_block'
                    WHERE id = :attempt_id
                    """
                ),
                {"attempt_id": trace.provider_attempt_id, "completed_at": now},
            )
            await reconcile_budget_reservations(
                connection,
                trace.execution_id,
                actual_tokens=0,
                actual_cost=Decimal(0),
                now=now,
            )
            await self._finish_span(
                connection,
                trace.provider_span_id,
                "blocked",
                0,
                now,
                "model_policy_block",
            )
            await self._finish_span(
                connection,
                trace.root_span_id,
                "blocked",
                0,
                now,
                "model_policy_block",
            )
            await connection.execute(
                text(
                    """
                    UPDATE control.executions
                    SET status = 'blocked', completed_at = :completed_at,
                        final_reason = 'policy_block',
                        error_code = 'model_policy_block',
                        metadata = metadata || CAST(:metadata AS jsonb)
                    WHERE id = :execution_id
                    """
                ),
                {
                    "execution_id": trace.execution_id,
                    "completed_at": now,
                    "metadata": json.dumps(
                        {
                            "recovery_state": "checkpointed",
                            "preflight_reason": assessment.reason,
                        }
                    ),
                },
            )
            checkpoint_id = await self._insert_model_policy_checkpoint(
                connection,
                trace,
                model,
                decision_id,
                assessment,
                evidence,
                now,
            )
            await self._insert_model_policy_incident(
                connection,
                trace.execution_id,
                decision_id,
                policy_span_id,
                "critical",
                "Model call blocked",
                evidence,
            )
            return checkpoint_id

    @staticmethod
    async def _insert_model_policy_incident(
        connection,  # type: ignore[no-untyped-def]
        execution_id: UUID,
        decision_id: UUID,
        span_id: UUID,
        severity: str,
        title: str,
        evidence: dict[str, object],
    ) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO control.incidents (
                    execution_id, policy_decision_id, triggering_span_id,
                    incident_type, severity, title, evidence
                ) VALUES (
                    :execution_id, :decision_id, :span_id,
                    'manual_intervention', :severity, :title,
                    CAST(:evidence AS jsonb)
                )
                """
            ),
            {
                "execution_id": execution_id,
                "decision_id": decision_id,
                "span_id": span_id,
                "severity": severity,
                "title": title,
                "evidence": json.dumps(evidence),
            },
        )

    @staticmethod
    async def _insert_model_policy_checkpoint(
        connection,  # type: ignore[no-untyped-def]
        trace: ExecutionTrace,
        model: str,
        decision_id: UUID,
        assessment: ModelPolicyAssessment,
        evidence: dict[str, object],
        now: datetime,
    ) -> UUID:
        projection = assessment.projection
        if projection is None:
            raise ValueError("A blocked admission requires a model policy projection")
        packet = {
            "version": "1.0",
            "task": f"Complete a chat request with {model}",
            "source_execution_id": str(trace.execution_id),
            "source_provider": trace.provider_name,
            "source_model": model,
            "completed_work": [],
            "failed_operation": {
                "name": "chat.completion",
                "arguments": {
                    "provider": trace.provider_name,
                    "model": model,
                    "projected_tokens": projection.projected_tokens,
                },
            },
            "reason_for_intervention": assessment.reason,
            "recommended_action": (
                "Select an allowed model, reduce max_tokens, or update the project policy"
            ),
            "evidence": evidence,
            "created_at": now.isoformat(),
        }
        canonical = json.dumps(packet, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return UUID(
            str(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO control.continuity_checkpoints (
                                execution_id, policy_decision_id,
                                content_fingerprint, packet
                            ) VALUES (
                                :execution_id, :decision_id,
                                :fingerprint, CAST(:packet AS jsonb)
                            )
                            RETURNING id
                            """
                        ),
                        {
                            "execution_id": trace.execution_id,
                            "decision_id": decision_id,
                            "fingerprint": fingerprint,
                            "packet": json.dumps(packet),
                        },
                    )
                ).scalar_one()
            )
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
