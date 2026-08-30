import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from control_schemas import (
    ContinuityPacket,
    RecoveryStrategy,
    RuntimeActionCheckRequest,
    RuntimeActionCompleted,
    RuntimeActionCompleteRequest,
    RuntimeActionDecision,
    RuntimeCancellationResult,
    RuntimeCheckpoint,
    RuntimeDecision,
    RuntimeExecutionCreated,
    RuntimeExecutionRequest,
    RuntimeIntervention,
    RuntimePolicyMode,
    RuntimePreflightRequest,
    RuntimePreflightResult,
    RuntimeRecoveryRequest,
    RuntimeRecoveryResult,
)
from sqlalchemy import text

from app.domain.auth import ApiKeyPrincipal
from app.domain.preflight import (
    BudgetSnapshot,
    PreflightAssessment,
    PreflightExecution,
    evaluate_preflight,
)
from app.domain.runtime import (
    ActionHistoryItem,
    evaluate_loop,
    fingerprint,
    operation_fingerprint,
    sanitize_value,
)
from app.infrastructure.database import Database


class RuntimeExecutionNotFoundError(Exception):
    pass


class RuntimeExecutionNotActiveError(Exception):
    def __init__(self, status: str) -> None:
        super().__init__(f"Execution is {status}")
        self.status = status


class RuntimeActionNotFoundError(Exception):
    pass


class RuntimeRecoveryError(Exception):
    pass


class RuntimeRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def authorize_execution(
        self, principal: ApiKeyPrincipal, execution_id: UUID
    ) -> None:
        async with self._database.connect() as connection:
            authorized = (
                await connection.execute(
                    text(
                        """
                        SELECT 1
                        FROM control.executions
                        WHERE id = :execution_id AND project_id = :project_id
                        """
                    ),
                    {
                        "execution_id": execution_id,
                        "project_id": principal.project_id,
                    },
                )
            ).scalar_one_or_none()
        if authorized is None:
            raise RuntimeExecutionNotFoundError

    async def start(
        self,
        principal: ApiKeyPrincipal,
        request: RuntimeExecutionRequest,
    ) -> RuntimeExecutionCreated:
        request_id = f"run_{uuid4().hex}"
        task = str(sanitize_value(request.task))
        metadata = {
            "task": task,
            "runtime_policy": {
                "mode": request.policy_mode.value,
                "repeat_threshold": request.repeat_threshold,
                "window_size": request.window_size,
            },
            "recovery_state": "not_required",
        }
        async with self._database.begin() as connection:
            row = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO control.executions (
                            request_id, organization_id, project_id,
                            application_id, agent_id, status, requested_model,
                            active_provider, active_model, is_streaming,
                            input_fingerprint, metadata
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
                            'running', :model, :provider, :model, false,
                            :input_fingerprint, CAST(:metadata AS jsonb)
                        )
                        RETURNING id, request_id, status
                        """
                    ),
                    {
                        "request_id": request_id,
                        "organization_id": principal.organization_id,
                        "project_id": principal.project_id,
                        "application_slug": request.application_slug,
                        "agent_slug": request.agent_slug,
                        "model": request.model,
                        "provider": request.provider,
                        "input_fingerprint": fingerprint(task),
                        "metadata": json.dumps(metadata),
                    },
                )
            ).mappings().one()
            await connection.execute(
                text(
                    """
                    INSERT INTO control.spans (
                        execution_id, sequence_no, kind, name, attributes
                    ) VALUES (
                        :execution_id, 1, 'gateway', 'runtime.execution',
                        CAST(:attributes AS jsonb)
                    )
                    """
                ),
                {
                    "execution_id": row["id"],
                    "attributes": json.dumps(
                        {
                            "policy_mode": request.policy_mode.value,
                            "repeat_threshold": request.repeat_threshold,
                        }
                    ),
                },
            )
        return RuntimeExecutionCreated(
            execution_id=row["id"],
            trace_id=row["request_id"],
            status=row["status"],
            repeat_threshold=request.repeat_threshold,
            policy_mode=request.policy_mode,
        )

    async def get_preflight_execution(
        self,
        principal: ApiKeyPrincipal,
        execution_id: UUID,
    ) -> PreflightExecution:
        async with self._database.connect() as connection:
            execution = (
                await connection.execute(
                    text(
                        """
                        SELECT id, status, organization_id, project_id, user_id,
                               application_id, agent_id, active_provider,
                               active_model, requested_model
                        FROM control.executions
                        WHERE id = :execution_id AND project_id = :project_id
                        """
                    ),
                    {
                        "execution_id": execution_id,
                        "project_id": principal.project_id,
                    },
                )
            ).mappings().one_or_none()
            if execution is None:
                raise RuntimeExecutionNotFoundError
            if execution["status"] != "running":
                raise RuntimeExecutionNotActiveError(execution["status"])

        return PreflightExecution(
            execution_id=execution_id,
            provider=execution["active_provider"] or "custom",
            model=execution["active_model"] or execution["requested_model"],
        )

    async def record_preflight(
        self,
        principal: ApiKeyPrincipal,
        execution: PreflightExecution,
        request: RuntimePreflightRequest,
        *,
        context_window_tokens: int,
        safety_margin_tokens: int,
        warning_utilization: float,
    ) -> RuntimePreflightResult:
        checkpoint_id: UUID | None = None
        async with self._database.begin() as connection:
            locked = await self._locked_execution(
                connection, principal.project_id, execution.execution_id
            )
            if locked["status"] != "running":
                raise RuntimeExecutionNotActiveError(locked["status"])
            # Keep the budget snapshot and reservation atomic across the organization.
            await connection.execute(
                text(
                    "SELECT pg_advisory_xact_lock("
                    "hashtextextended(CAST(:organization_id AS text), 0))"
                ),
                {"organization_id": str(principal.organization_id)},
            )
            budgets = await self._preflight_budget_snapshots(
                connection, locked, execution.execution_id
            )
            assessment = evaluate_preflight(
                request,
                budgets,
                context_window_tokens=context_window_tokens,
                safety_margin_tokens=safety_margin_tokens,
                warning_utilization=warning_utilization,
            )
            evidence = {
                "input_tokens": request.input_tokens,
                "reserved_output_tokens": request.requested_output_tokens,
                "safety_margin_tokens": safety_margin_tokens,
                "projected_context_tokens": assessment.projected_context_tokens,
                "context_window_tokens": context_window_tokens,
                "context_remaining_tokens": assessment.context_remaining_tokens,
                "context_utilization": assessment.context_utilization,
                "budgets": [
                    budget.model_dump(mode="json") for budget in assessment.budgets
                ],
            }
            now = await self._database_now(connection)
            blocked = assessment.decision is RuntimeDecision.BLOCK
            if not blocked:
                await self._reserve_preflight_budget(
                    connection,
                    execution.execution_id,
                    assessment,
                    request,
                    now,
                )
            span_id = UUID(
                str(
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO control.spans (
                                    execution_id, parent_span_id, sequence_no,
                                    kind, name, status, completed_at,
                                    duration_ms, error_code, attributes
                                ) VALUES (
                                    :execution_id, :root_span_id, :sequence_no,
                                    'policy', 'Model context and budget preflight',
                                    :status, :now, 0, :error_code,
                                    CAST(:attributes AS jsonb)
                                )
                                RETURNING id
                                """
                            ),
                            {
                                "execution_id": execution.execution_id,
                                "root_span_id": locked["root_span_id"],
                                "sequence_no": locked["next_sequence_no"],
                                "status": "blocked" if blocked else "completed",
                                "now": now,
                                "error_code": "model_preflight_block" if blocked else None,
                                "attributes": json.dumps(evidence),
                            },
                        )
                    ).scalar_one()
                )
            )
            decision_id = UUID(
                str(
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO control.policy_decisions (
                                    execution_id, triggering_span_id,
                                    budget_policy_id, policy_code,
                                    policy_version, mode, outcome,
                                    final_execution_state, evidence
                                ) VALUES (
                                    :execution_id, :span_id, :budget_policy_id,
                                    'model_preflight', '1.0', :mode, :outcome,
                                    :final_state, CAST(:evidence AS jsonb)
                                )
                                RETURNING id
                                """
                            ),
                            {
                                "execution_id": execution.execution_id,
                                "span_id": span_id,
                                "budget_policy_id": assessment.blocking_policy_id,
                                "mode": assessment.mode.value,
                                "outcome": assessment.decision.value,
                                "final_state": "blocked" if blocked else "running",
                                "evidence": json.dumps(
                                    {"reason": assessment.reason, **evidence}
                                ),
                            },
                        )
                    ).scalar_one()
                )
            )
            if blocked:
                await connection.execute(
                    text(
                        """
                        UPDATE control.spans
                        SET status = 'blocked', completed_at = :now,
                            duration_ms = GREATEST(
                                0, round(extract(epoch FROM (
                                    :now - started_at
                                )) * 1000)::integer
                            ), error_code = 'model_preflight_block'
                        WHERE id = :root_span_id
                        """
                    ),
                    {"root_span_id": locked["root_span_id"], "now": now},
                )
                await connection.execute(
                    text(
                        """
                        UPDATE control.executions
                        SET status = 'blocked', completed_at = :now,
                            final_reason = 'policy_block',
                            error_code = 'model_preflight_block',
                            metadata = metadata || CAST(:metadata AS jsonb)
                        WHERE id = :execution_id
                        """
                    ),
                    {
                        "execution_id": execution.execution_id,
                        "now": now,
                        "metadata": json.dumps(
                            {
                                "recovery_state": "checkpointed",
                                "preflight_reason": assessment.reason,
                            }
                        ),
                    },
                )
                checkpoint_id = await self._create_checkpoint(
                    connection,
                    locked,
                    policy_decision_id=decision_id,
                    failed_operation={
                        "name": "model_call",
                        "arguments": {
                            "input_tokens": request.input_tokens,
                            "requested_output_tokens": request.requested_output_tokens,
                        },
                    },
                    reason=assessment.reason,
                    evidence=evidence,
                    now=now,
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO control.incidents (
                            execution_id, policy_decision_id, triggering_span_id,
                            incident_type, severity, title, evidence
                        ) VALUES (
                            :execution_id, :policy_decision_id, :span_id,
                            :incident_type, 'critical', 'Model call blocked',
                            CAST(:evidence AS jsonb)
                        )
                        """
                    ),
                    {
                        "execution_id": execution.execution_id,
                        "policy_decision_id": decision_id,
                        "span_id": span_id,
                        "incident_type": (
                            "budget_exceeded"
                            if assessment.blocking_policy_id
                            else "manual_intervention"
                        ),
                        "evidence": json.dumps(
                            {"reason": assessment.reason, **evidence}
                        ),
                    },
                )

        return RuntimePreflightResult(
            execution_id=execution.execution_id,
            decision=assessment.decision,
            reason=assessment.reason,
            provider=execution.provider,
            model=execution.model,
            input_tokens=request.input_tokens,
            reserved_output_tokens=request.requested_output_tokens,
            safety_margin_tokens=safety_margin_tokens,
            projected_context_tokens=assessment.projected_context_tokens,
            context_window_tokens=context_window_tokens,
            context_remaining_tokens=assessment.context_remaining_tokens,
            context_utilization=assessment.context_utilization,
            budgets=assessment.budgets,
            checkpoint_id=checkpoint_id,
        )

    async def check_action(
        self,
        principal: ApiKeyPrincipal,
        execution_id: UUID,
        request: RuntimeActionCheckRequest,
    ) -> RuntimeActionDecision:
        sanitized_arguments = sanitize_value(request.arguments)
        operation = operation_fingerprint(request.kind, request.name, request.arguments)
        async with self._database.begin() as connection:
            execution = await self._locked_execution(
                connection, principal.project_id, execution_id
            )
            now = await self._database_now(connection)
            if execution["status"] != "running":
                raise RuntimeExecutionNotActiveError(execution["status"])
            metadata = dict(execution["metadata"] or {})
            policy = dict(metadata.get("runtime_policy") or {})
            threshold = int(policy.get("repeat_threshold", 3))
            window_size = int(policy.get("window_size", 12))
            mode = RuntimePolicyMode(policy.get("mode", RuntimePolicyMode.ENFORCE))
            history_rows = (
                await connection.execute(
                    text(
                        """
                        SELECT operation_fingerprint, attributes
                        FROM control.spans
                        WHERE execution_id = :execution_id
                          AND kind IN ('tool', 'provider')
                          AND operation_fingerprint IS NOT NULL
                        ORDER BY sequence_no DESC
                        LIMIT :window_size
                        """
                    ),
                    {"execution_id": execution_id, "window_size": window_size},
                )
            ).mappings().all()
            history = [
                ActionHistoryItem(
                    operation_fingerprint=row["operation_fingerprint"],
                    result_fingerprint=(row["attributes"] or {}).get(
                        "result_fingerprint"
                    ),
                    progress=(row["attributes"] or {}).get("progress"),
                )
                for row in reversed(history_rows)
            ]
            evaluation = evaluate_loop(
                operation, history, threshold, window_size, mode
            )
            observation_occurrence = int(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT COALESCE(max(occurrence_no), 0) + 1
                            FROM control.loop_observations
                            WHERE execution_id = :execution_id
                              AND operation_fingerprint = :operation_fingerprint
                            """
                        ),
                        {
                            "execution_id": execution_id,
                            "operation_fingerprint": operation,
                        },
                    )
                ).scalar_one()
            )
            sequence_no = int(execution["next_sequence_no"])
            span_status = (
                "blocked"
                if evaluation.decision is RuntimeDecision.BLOCK
                else "running"
            )
            span_kind = "tool" if request.kind == "tool" else "provider"
            attributes = {
                "arguments": sanitized_arguments,
                "decision": evaluation.decision.value,
                **evaluation.evidence,
            }
            action_id = UUID(
                str(
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO control.spans (
                                    execution_id, parent_span_id, sequence_no,
                                    kind, name, tool_name, status,
                                    operation_fingerprint, completed_at,
                                    duration_ms, error_code, attributes
                                ) VALUES (
                                    :execution_id, :root_span_id, :sequence_no,
                                    :kind, :name, :tool_name, :status,
                                    :operation_fingerprint, :completed_at,
                                    :duration_ms, :error_code,
                                    CAST(:attributes AS jsonb)
                                )
                                RETURNING id
                                """
                            ),
                            {
                                "execution_id": execution_id,
                                "root_span_id": execution["root_span_id"],
                                "sequence_no": sequence_no,
                                "kind": span_kind,
                                "name": request.name,
                                "tool_name": request.name if span_kind == "tool" else None,
                                "status": span_status,
                                "operation_fingerprint": operation,
                                "completed_at": now if span_status == "blocked" else None,
                                "duration_ms": 0 if span_status == "blocked" else None,
                                "error_code": (
                                    "max_tool_repeats"
                                    if span_status == "blocked"
                                    else None
                                ),
                                "attributes": json.dumps(attributes),
                            },
                        )
                    ).scalar_one()
                )
            )
            observation_action = evaluation.decision.value
            await connection.execute(
                text(
                    """
                    INSERT INTO control.loop_observations (
                        execution_id, span_id, operation_fingerprint,
                        occurrence_no, window_size, action, evidence
                    ) VALUES (
                        :execution_id, :span_id, :operation_fingerprint,
                        :occurrence_no, :window_size, :action,
                        CAST(:evidence AS jsonb)
                    )
                    """
                ),
                {
                    "execution_id": execution_id,
                    "span_id": action_id,
                    "operation_fingerprint": operation,
                    "occurrence_no": observation_occurrence,
                    "window_size": window_size,
                    "action": observation_action,
                    "evidence": json.dumps(evaluation.evidence),
                },
            )
            final_state = "blocked" if span_status == "blocked" else "running"
            policy_decision_id = UUID(
                str(
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO control.policy_decisions (
                                    execution_id, triggering_span_id, policy_code,
                                    policy_version, mode, outcome,
                                    final_execution_state, evidence
                                ) VALUES (
                                    :execution_id, :span_id, 'no_progress_loop',
                                    '1.0', :mode, :outcome, :final_state,
                                    CAST(:evidence AS jsonb)
                                )
                                RETURNING id
                                """
                            ),
                            {
                                "execution_id": execution_id,
                                "span_id": action_id,
                                "mode": mode.value,
                                "outcome": evaluation.decision.value,
                                "final_state": final_state,
                                "evidence": json.dumps(
                                    {
                                        **evaluation.evidence,
                                        "reason": evaluation.reason,
                                        "operation_fingerprint": operation,
                                    }
                                ),
                            },
                        )
                    ).scalar_one()
                )
            )
            checkpoint_id: UUID | None = None
            if evaluation.decision is RuntimeDecision.BLOCK:
                checkpoint_id = await self._block_and_checkpoint(
                    connection=connection,
                    execution=execution,
                    action_id=action_id,
                    action_name=request.name,
                    arguments=sanitized_arguments,
                    evaluation_reason=evaluation.reason,
                    evidence=evaluation.evidence,
                    policy_decision_id=policy_decision_id,
                    sequence_no=sequence_no + 1,
                    now=now,
                )
        return RuntimeActionDecision(
            execution_id=execution_id,
            action_id=action_id,
            decision=evaluation.decision,
            operation_fingerprint=operation,
            occurrence=evaluation.occurrence,
            threshold=threshold,
            reason=evaluation.reason,
            evidence=evaluation.evidence,
            checkpoint_id=checkpoint_id,
        )

    async def complete_action(
        self,
        principal: ApiKeyPrincipal,
        execution_id: UUID,
        action_id: UUID,
        request: RuntimeActionCompleteRequest,
    ) -> RuntimeActionCompleted:
        result_hash = fingerprint(request.result)
        sanitized_summary = self._result_summary(request.result, request.summary)
        async with self._database.begin() as connection:
            execution = await self._locked_execution(
                connection, principal.project_id, execution_id
            )
            now = await self._database_now(connection)
            if execution["status"] != "running":
                raise RuntimeExecutionNotActiveError(execution["status"])
            span = (
                await connection.execute(
                    text(
                        """
                        SELECT id, started_at
                        FROM control.spans
                        WHERE execution_id = :execution_id
                          AND id = :action_id
                          AND status = 'running'
                          AND kind IN ('tool', 'provider')
                        FOR UPDATE
                        """
                    ),
                    {"execution_id": execution_id, "action_id": action_id},
                )
            ).mappings().one_or_none()
            if span is None:
                raise RuntimeActionNotFoundError
            duration_ms = max(
                0, round((now - span["started_at"]).total_seconds() * 1000)
            )
            await connection.execute(
                text(
                    """
                    UPDATE control.spans
                    SET status = :status,
                        completed_at = :completed_at,
                        duration_ms = :duration_ms,
                        error_code = :error_code,
                        attributes = attributes || CAST(:attributes AS jsonb)
                    WHERE id = :action_id
                    """
                ),
                {
                    "action_id": action_id,
                    "status": request.status,
                    "completed_at": now,
                    "duration_ms": duration_ms,
                    "error_code": "action_failed" if request.status == "failed" else None,
                    "attributes": json.dumps(
                        {
                            "result_fingerprint": result_hash,
                            "result_summary": sanitized_summary,
                            "progress": request.progress,
                        }
                    ),
                },
            )
        return RuntimeActionCompleted(
            execution_id=execution_id,
            action_id=action_id,
            status=request.status,
            result_fingerprint=result_hash,
            progress=request.progress,
        )

    async def get_intervention(
        self, principal: ApiKeyPrincipal, execution_id: UUID
    ) -> RuntimeIntervention | None:
        async with self._database.connect() as connection:
            execution = (
                await connection.execute(
                    text(
                        """
                        SELECT status
                        FROM control.executions
                        WHERE id = :execution_id AND project_id = :project_id
                        """
                    ),
                    {"execution_id": execution_id, "project_id": principal.project_id},
                )
            ).mappings().one_or_none()
            if execution is None:
                raise RuntimeExecutionNotFoundError
            decision = (
                await connection.execute(
                    text(
                        """
                        SELECT policy_code, mode, outcome, evidence, decided_at
                        FROM control.policy_decisions
                        WHERE execution_id = :execution_id
                          AND outcome IN ('block', 'cancel', 'handoff')
                        ORDER BY decided_at DESC
                        LIMIT 1
                        """
                    ),
                    {"execution_id": execution_id},
                )
            ).mappings().one_or_none()
            if decision is None:
                return None
            checkpoint_row = (
                await connection.execute(
                    text(
                        """
                        SELECT id, execution_id, status, content_fingerprint,
                               packet, created_at, consumed_at
                        FROM control.continuity_checkpoints
                        WHERE execution_id = :execution_id
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"execution_id": execution_id},
                )
            ).mappings().one_or_none()
        evidence = dict(decision["evidence"] or {})
        return RuntimeIntervention(
            execution_id=execution_id,
            execution_status=execution["status"],
            policy_code=decision["policy_code"],
            policy_mode=decision["mode"],
            outcome=decision["outcome"],
            reason=str(evidence.get("reason", "Runtime policy intervened")),
            evidence=evidence,
            decided_at=decision["decided_at"],
            checkpoint=self._checkpoint_from_row(checkpoint_row),
        )

    async def cancel(
        self, principal: ApiKeyPrincipal, execution_id: UUID
    ) -> RuntimeCancellationResult:
        async with self._database.begin() as connection:
            execution = await self._locked_execution(
                connection, principal.project_id, execution_id
            )
            now = await self._database_now(connection)
            if execution["status"] != "running":
                raise RuntimeExecutionNotActiveError(execution["status"])
            sequence_no = int(execution["next_sequence_no"])
            policy_span_id = UUID(
                str(
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO control.spans (
                                    execution_id, parent_span_id, sequence_no,
                                    kind, name, status, completed_at, duration_ms,
                                    error_code, attributes
                                ) VALUES (
                                    :execution_id, :root_span_id, :sequence_no,
                                    'policy', 'Manual cancellation', 'cancelled',
                                    :now, 0, 'cancel_requested',
                                    '{"action":"cancel"}'::jsonb
                                )
                                RETURNING id
                                """
                            ),
                            {
                                "execution_id": execution_id,
                                "root_span_id": execution["root_span_id"],
                                "sequence_no": sequence_no,
                                "now": now,
                            },
                        )
                    ).scalar_one()
                )
            )
            await connection.execute(
                text(
                    """
                    UPDATE control.spans
                    SET status = 'cancelled', completed_at = :now,
                        duration_ms = GREATEST(
                            0, round(extract(epoch FROM (:now - started_at)) * 1000)::integer
                        ), error_code = COALESCE(error_code, 'cancel_requested')
                    WHERE execution_id = :execution_id AND status = 'running'
                    """
                ),
                {"execution_id": execution_id, "now": now},
            )
            await connection.execute(
                text(
                    """
                    UPDATE control.executions
                    SET status = 'cancelled', completed_at = :now,
                        final_reason = 'manual_cancel', error_code = 'cancel_requested',
                        metadata = metadata || '{"recovery_state":"checkpointed"}'::jsonb
                    WHERE id = :execution_id
                    """
                ),
                {"execution_id": execution_id, "now": now},
            )
            decision_id = UUID(
                str(
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO control.policy_decisions (
                                    execution_id, triggering_span_id, policy_code,
                                    policy_version, mode, outcome,
                                    final_execution_state, evidence
                                ) VALUES (
                                    :execution_id, :span_id, 'manual_cancel', '1.0',
                                    'enforce', 'cancel', 'cancelled',
                                    '{"reason":"Cancellation requested by operator"}'::jsonb
                                )
                                RETURNING id
                                """
                            ),
                            {"execution_id": execution_id, "span_id": policy_span_id},
                        )
                    ).scalar_one()
                )
            )
            checkpoint_id = await self._create_checkpoint(
                connection,
                execution,
                policy_decision_id=decision_id,
                failed_operation={"name": "manual_cancel", "arguments": {}},
                reason="Cancellation requested by operator",
                evidence={"action": "cancel"},
                now=now,
            )
        return RuntimeCancellationResult(
            execution_id=execution_id,
            status="cancelled",
            checkpoint_id=checkpoint_id,
        )

    async def recover(
        self,
        principal: ApiKeyPrincipal,
        execution_id: UUID,
        request: RuntimeRecoveryRequest,
    ) -> RuntimeRecoveryResult:
        async with self._database.begin() as connection:
            source = await self._locked_execution(
                connection, principal.project_id, execution_id
            )
            now = await self._database_now(connection)
            checkpoint_row = (
                await connection.execute(
                    text(
                        """
                        SELECT id, execution_id, status, content_fingerprint,
                               packet, created_at, consumed_at
                        FROM control.continuity_checkpoints
                        WHERE execution_id = :execution_id
                          AND status = 'available'
                        ORDER BY created_at DESC
                        LIMIT 1
                        FOR UPDATE
                        """
                    ),
                    {"execution_id": execution_id},
                )
            ).mappings().one_or_none()
            if checkpoint_row is None:
                raise RuntimeRecoveryError("No available checkpoint exists")
            checkpoint = self._checkpoint_from_row(checkpoint_row)
            if checkpoint is None:
                raise RuntimeRecoveryError("The available checkpoint is invalid")
            if request.strategy is RecoveryStrategy.STOP:
                await connection.execute(
                    text(
                        """
                        INSERT INTO control.recovery_attempts (
                            source_execution_id, checkpoint_id, strategy,
                            status, details, completed_at
                        ) VALUES (
                            :execution_id, :checkpoint_id, 'stop', 'stopped',
                            '{"reason":"Operator chose to stop"}'::jsonb, :now
                        )
                        """
                    ),
                    {
                        "execution_id": execution_id,
                        "checkpoint_id": checkpoint.id,
                        "now": now,
                    },
                )
                return RuntimeRecoveryResult(
                    source_execution_id=execution_id,
                    strategy=request.strategy,
                    status="stopped",
                    checkpoint=checkpoint,
                    message="Execution remains stopped; the checkpoint is available for audit.",
                )

            target_provider = request.target_provider or source["active_provider"] or "custom"
            target_model = request.target_model or source["active_model"] or source["requested_model"]
            if (
                request.strategy is RecoveryStrategy.MODEL_HANDOFF
                and target_provider == source["active_provider"]
                and target_model == source["active_model"]
            ):
                raise RuntimeRecoveryError("A model handoff must select a different target")
            resumed_id = uuid4()
            resumed_request_id = f"run_{uuid4().hex}"
            source_metadata = dict(source["metadata"] or {})
            resumed_metadata = {
                "task": source_metadata.get("task", checkpoint.packet.task),
                "runtime_policy": source_metadata.get("runtime_policy", {}),
                "recovered_from": str(execution_id),
                "checkpoint_id": str(checkpoint.id),
                "recovery_strategy": request.strategy.value,
                "modified_arguments": sanitize_value(request.modified_arguments or {}),
                "recovery_state": "resumed",
            }
            await connection.execute(
                text(
                    """
                    INSERT INTO control.executions (
                        id, request_id, organization_id, project_id,
                        application_id, agent_id, status, requested_model,
                        active_provider, active_model, is_streaming,
                        input_fingerprint, metadata
                    ) VALUES (
                        :id, :request_id, :organization_id, :project_id,
                        :application_id, :agent_id, 'running', :model,
                        :provider, :model, false, :input_fingerprint,
                        CAST(:metadata AS jsonb)
                    )
                    """
                ),
                {
                    "id": resumed_id,
                    "request_id": resumed_request_id,
                    "organization_id": source["organization_id"],
                    "project_id": source["project_id"],
                    "application_id": source["application_id"],
                    "agent_id": source["agent_id"],
                    "model": target_model,
                    "provider": target_provider,
                    "input_fingerprint": checkpoint.content_fingerprint,
                    "metadata": json.dumps(resumed_metadata),
                },
            )
            root_id = UUID(
                str(
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO control.spans (
                                    execution_id, sequence_no, kind, name, attributes
                                ) VALUES (
                                    :execution_id, 1, 'gateway', 'runtime.execution',
                                    CAST(:attributes AS jsonb)
                                )
                                RETURNING id
                                """
                            ),
                            {
                                "execution_id": resumed_id,
                                "attributes": json.dumps(
                                    {
                                        "recovered_from": str(execution_id),
                                        "checkpoint_id": str(checkpoint.id),
                                    }
                                ),
                            },
                        )
                    ).scalar_one()
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO control.spans (
                        execution_id, parent_span_id, sequence_no, kind,
                        name, status, completed_at, duration_ms, attributes
                    ) VALUES (
                        :execution_id, :root_id, 2, 'handoff',
                        'Continuity checkpoint loaded', 'completed', :now, 0,
                        CAST(:attributes AS jsonb)
                    )
                    """
                ),
                {
                    "execution_id": resumed_id,
                    "root_id": root_id,
                    "now": now,
                    "attributes": json.dumps(
                        {
                            "strategy": request.strategy.value,
                            "source_execution_id": str(execution_id),
                            "checkpoint_id": str(checkpoint.id),
                        }
                    ),
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO control.recovery_attempts (
                        source_execution_id, resumed_execution_id,
                        checkpoint_id, strategy, target_provider, target_model,
                        status, details
                    ) VALUES (
                        :source_execution_id, :resumed_execution_id,
                        :checkpoint_id, :strategy, :target_provider, :target_model,
                        'prepared', CAST(:details AS jsonb)
                    )
                    """
                ),
                {
                    "source_execution_id": execution_id,
                    "resumed_execution_id": resumed_id,
                    "checkpoint_id": checkpoint.id,
                    "strategy": request.strategy.value,
                    "target_provider": target_provider,
                    "target_model": target_model,
                    "details": json.dumps(
                        {"modified_arguments": sanitize_value(request.modified_arguments or {})}
                    ),
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    """
                    UPDATE control.continuity_checkpoints
                    SET status = 'consumed', consumed_at = :now
                    WHERE id = :checkpoint_id
                    """
                ),
                {"checkpoint_id": checkpoint.id, "now": now},
            )
            if request.strategy is RecoveryStrategy.MODEL_HANDOFF:
                await connection.execute(
                    text(
                        """
                        UPDATE control.executions
                        SET status = 'handed_off', final_reason = 'model_handoff',
                            metadata = metadata || CAST(:metadata AS jsonb)
                        WHERE id = :execution_id
                        """
                    ),
                    {
                        "execution_id": execution_id,
                        "metadata": json.dumps({"resumed_execution_id": str(resumed_id)}),
                    },
                )
            consumed_checkpoint = checkpoint.model_copy(
                update={"status": "consumed", "consumed_at": now}
            )
        return RuntimeRecoveryResult(
            source_execution_id=execution_id,
            strategy=request.strategy,
            status="prepared",
            resumed_execution_id=resumed_id,
            target_provider=target_provider,
            target_model=target_model,
            checkpoint=consumed_checkpoint,
            message=(
                "A new execution was prepared with the verified continuity packet."
            ),
        )

    async def _locked_execution(self, connection, project_id: UUID, execution_id: UUID):  # type: ignore[no-untyped-def]
        row = (
            await connection.execute(
                text(
                    """
                    SELECT execution.*,
                           root.id AS root_span_id,
                           COALESCE((
                               SELECT max(sequence_no) + 1
                               FROM control.spans
                               WHERE execution_id = execution.id
                           ), 1) AS next_sequence_no
                    FROM control.executions execution
                    LEFT JOIN control.spans root
                      ON root.execution_id = execution.id
                     AND root.sequence_no = 1
                    WHERE execution.id = :execution_id
                      AND execution.project_id = :project_id
                    FOR UPDATE OF execution
                    """
                ),
                {"execution_id": execution_id, "project_id": project_id},
            )
        ).mappings().one_or_none()
        if row is None:
            raise RuntimeExecutionNotFoundError
        return row

    async def _preflight_budget_snapshots(
        self, connection, execution, execution_id: UUID  # type: ignore[no-untyped-def]
    ) -> list[BudgetSnapshot]:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT policy.id, policy.name, policy.scope_type,
                           policy.period_type, policy.mode,
                           policy.max_requests, policy.max_tokens,
                           policy.max_cost,
                           COALESCE(consumption.requests, 0)
                             + COALESCE(reservations.requests, 0)
                               AS consumed_requests,
                           COALESCE(consumption.tokens, 0)
                             + COALESCE(reservations.tokens, 0)
                               AS consumed_tokens,
                           COALESCE(consumption.cost, 0)
                             + COALESCE(reservations.cost, 0)
                               AS consumed_cost
                    FROM control.budget_policies policy
                    LEFT JOIN LATERAL (
                        SELECT count(DISTINCT attempt.id) AS requests,
                               COALESCE(sum(usage.total_tokens), 0) AS tokens,
                               COALESCE(sum(usage.cost_amount), 0) AS cost
                        FROM control.executions consumed
                        LEFT JOIN control.provider_attempts attempt
                          ON attempt.execution_id = consumed.id
                        LEFT JOIN control.usage_records usage
                          ON usage.provider_attempt_id = attempt.id
                        WHERE (
                            (policy.scope_type = 'organization'
                             AND consumed.organization_id = policy.scope_id)
                            OR (policy.scope_type = 'project'
                                AND consumed.project_id = policy.scope_id)
                            OR (policy.scope_type = 'user'
                                AND consumed.user_id = policy.scope_id)
                            OR (policy.scope_type = 'application'
                                AND consumed.application_id = policy.scope_id)
                            OR (policy.scope_type = 'agent'
                                AND consumed.agent_id = policy.scope_id)
                        )
                          AND consumed.started_at >= policy.starts_at
                          AND (
                              policy.period_type = 'execution'
                              AND consumed.id = :execution_id
                              OR policy.period_type = 'daily'
                              AND consumed.started_at >= date_trunc('day', now())
                              OR policy.period_type = 'monthly'
                              AND consumed.started_at >= date_trunc('month', now())
                              OR policy.period_type = 'rolling'
                              AND consumed.started_at >= now() - make_interval(
                                  secs => policy.window_seconds
                              )
                          )
                    ) consumption ON true
                    LEFT JOIN LATERAL (
                        SELECT COALESCE(sum(GREATEST(
                                   reserved.reserved_requests
                                     - reserved.claimed_requests,
                                   0
                               )), 0) AS requests,
                               COALESCE(sum(reserved.reserved_tokens), 0) AS tokens,
                               COALESCE(sum(reserved.reserved_cost), 0) AS cost
                        FROM control.budget_reservations reserved
                        JOIN control.executions reserved_execution
                          ON reserved_execution.id = reserved.execution_id
                        WHERE reserved.budget_policy_id = policy.id
                          AND reserved.status = 'active'
                          AND reserved.expires_at > now()
                          AND reserved_execution.started_at >= policy.starts_at
                          AND (
                              policy.period_type = 'execution'
                              AND reserved_execution.id = :execution_id
                              OR policy.period_type = 'daily'
                              AND reserved_execution.started_at >= date_trunc('day', now())
                              OR policy.period_type = 'monthly'
                              AND reserved_execution.started_at >= date_trunc('month', now())
                              OR policy.period_type = 'rolling'
                              AND reserved_execution.started_at >= now() - make_interval(
                                  secs => policy.window_seconds
                              )
                          )
                    ) reservations ON true
                    WHERE policy.is_enabled
                      AND policy.starts_at <= now()
                      AND (policy.ends_at IS NULL OR policy.ends_at > now())
                      AND (
                          (policy.scope_type = 'organization'
                           AND policy.scope_id = :organization_id)
                          OR (policy.scope_type = 'project'
                              AND policy.scope_id = :project_id)
                          OR (policy.scope_type = 'user'
                              AND policy.scope_id = :user_id)
                          OR (policy.scope_type = 'application'
                              AND policy.scope_id = :application_id)
                          OR (policy.scope_type = 'agent'
                              AND policy.scope_id = :agent_id)
                      )
                    ORDER BY policy.scope_type, policy.name
                    """
                ),
                {
                    "execution_id": execution_id,
                    "organization_id": execution["organization_id"],
                    "project_id": execution["project_id"],
                    "user_id": execution["user_id"],
                    "application_id": execution["application_id"],
                    "agent_id": execution["agent_id"],
                },
            )
        ).mappings().all()
        return [
            BudgetSnapshot(
                policy_id=row["id"],
                name=row["name"],
                scope_type=row["scope_type"],
                period_type=row["period_type"],
                mode=RuntimePolicyMode(row["mode"]),
                consumed_requests=int(row["consumed_requests"]),
                consumed_tokens=int(row["consumed_tokens"]),
                consumed_cost=row["consumed_cost"],
                max_requests=row["max_requests"],
                max_tokens=row["max_tokens"],
                max_cost=row["max_cost"],
            )
            for row in rows
        ]

    @staticmethod
    async def _reserve_preflight_budget(
        connection,  # type: ignore[no-untyped-def]
        execution_id: UUID,
        assessment: PreflightAssessment,
        request: RuntimePreflightRequest,
        now: datetime,
    ) -> None:
        for budget in assessment.budgets:
            await connection.execute(
                text(
                    """
                    INSERT INTO control.budget_reservations (
                        budget_policy_id, execution_id, status,
                        reserved_requests, reserved_tokens, reserved_cost,
                        expires_at
                    ) VALUES (
                        :policy_id, :execution_id, 'active', 1,
                        :tokens, :cost,
                        CAST(:now AS timestamptz) + interval '15 minutes'
                    )
                    ON CONFLICT (budget_policy_id, execution_id) DO UPDATE
                    SET status = 'active',
                        reserved_requests = CASE
                            WHEN budget_reservations.status = 'active'
                             AND budget_reservations.expires_at > :now
                            THEN budget_reservations.reserved_requests + 1
                            ELSE 1
                        END,
                        claimed_requests = CASE
                            WHEN budget_reservations.status = 'active'
                             AND budget_reservations.expires_at > :now
                            THEN budget_reservations.claimed_requests
                            ELSE 0
                        END,
                        reserved_tokens = CASE
                            WHEN budget_reservations.status = 'active'
                             AND budget_reservations.expires_at > :now
                            THEN budget_reservations.reserved_tokens
                                 + EXCLUDED.reserved_tokens
                            ELSE EXCLUDED.reserved_tokens
                        END,
                        reserved_cost = CASE
                            WHEN budget_reservations.status = 'active'
                             AND budget_reservations.expires_at > :now
                            THEN budget_reservations.reserved_cost
                                 + EXCLUDED.reserved_cost
                            ELSE EXCLUDED.reserved_cost
                        END,
                        actual_requests = CASE
                            WHEN budget_reservations.status = 'active'
                             AND budget_reservations.expires_at > :now
                            THEN COALESCE(
                                budget_reservations.actual_requests, 0
                            )
                            ELSE 0
                        END,
                        actual_tokens = CASE
                            WHEN budget_reservations.status = 'active'
                             AND budget_reservations.expires_at > :now
                            THEN budget_reservations.actual_tokens
                            ELSE NULL
                        END,
                        actual_cost = CASE
                            WHEN budget_reservations.status = 'active'
                             AND budget_reservations.expires_at > :now
                            THEN budget_reservations.actual_cost
                            ELSE NULL
                        END,
                        created_at = CASE
                            WHEN budget_reservations.status = 'active'
                             AND budget_reservations.expires_at > :now
                            THEN budget_reservations.created_at
                            ELSE :now
                        END,
                        expires_at = EXCLUDED.expires_at,
                        reconciled_at = NULL
                    """
                ),
                {
                    "policy_id": budget.policy_id,
                    "execution_id": execution_id,
                    "tokens": request.input_tokens + request.requested_output_tokens,
                    "cost": request.estimated_cost,
                    "now": now,
                },
            )

    @staticmethod
    async def _database_now(connection) -> datetime:  # type: ignore[no-untyped-def]
        return (await connection.execute(text("SELECT clock_timestamp()"))).scalar_one()

    async def _block_and_checkpoint(
        self,
        connection,  # type: ignore[no-untyped-def]
        execution,
        action_id: UUID,
        action_name: str,
        arguments: Any,
        evaluation_reason: str,
        evidence: dict[str, object],
        policy_decision_id: UUID,
        sequence_no: int,
        now: datetime,
    ) -> UUID:
        await connection.execute(
            text(
                """
                INSERT INTO control.spans (
                    execution_id, parent_span_id, sequence_no, kind, name,
                    status, completed_at, duration_ms, error_code, attributes
                ) VALUES (
                    :execution_id, :root_span_id, :sequence_no, 'policy',
                    'No-progress circuit breaker', 'blocked', :now, 0,
                    'max_tool_repeats', CAST(:attributes AS jsonb)
                )
                """
            ),
            {
                "execution_id": execution["id"],
                "root_span_id": execution["root_span_id"],
                "sequence_no": sequence_no,
                "now": now,
                "attributes": json.dumps(
                    {"triggering_span_id": str(action_id), **evidence}
                ),
            },
        )
        await connection.execute(
            text(
                """
                UPDATE control.spans
                SET status = 'blocked', completed_at = :now,
                    duration_ms = GREATEST(
                        0, round(extract(epoch FROM (:now - started_at)) * 1000)::integer
                    ), error_code = 'max_tool_repeats'
                WHERE id = :root_span_id
                """
            ),
            {"root_span_id": execution["root_span_id"], "now": now},
        )
        await connection.execute(
            text(
                """
                UPDATE control.executions
                SET status = 'blocked', completed_at = :now,
                    final_reason = 'policy_block', error_code = 'max_tool_repeats',
                    metadata = metadata || CAST(:metadata AS jsonb)
                WHERE id = :execution_id
                """
            ),
            {
                "execution_id": execution["id"],
                "now": now,
                "metadata": json.dumps(
                    {
                        "repeat_count": evidence.get("occurrence", 0),
                        "repeat_threshold": evidence.get("threshold", 0),
                        "recovery_state": "checkpointed",
                    }
                ),
            },
        )
        await connection.execute(
            text(
                """
                INSERT INTO control.incidents (
                    execution_id, policy_decision_id, triggering_span_id,
                    incident_type, severity, title, evidence
                ) VALUES (
                    :execution_id, :policy_decision_id, :span_id,
                    'runaway_loop', 'critical', 'No-progress loop blocked',
                    CAST(:evidence AS jsonb)
                )
                """
            ),
            {
                "execution_id": execution["id"],
                "policy_decision_id": policy_decision_id,
                "span_id": action_id,
                "evidence": json.dumps(
                    {"reason": evaluation_reason, **evidence}
                ),
            },
        )
        return await self._create_checkpoint(
            connection,
            execution,
            policy_decision_id=policy_decision_id,
            failed_operation={"name": action_name, "arguments": arguments},
            reason=evaluation_reason,
            evidence=evidence,
            now=now,
        )

    async def _create_checkpoint(
        self,
        connection,  # type: ignore[no-untyped-def]
        execution,
        policy_decision_id: UUID,
        failed_operation: dict[str, Any],
        reason: str,
        evidence: dict[str, object],
        now: datetime,
    ) -> UUID:
        completed_rows = (
            await connection.execute(
                text(
                    """
                    SELECT attributes->>'result_summary' AS summary
                    FROM control.spans
                    WHERE execution_id = :execution_id
                      AND status = 'completed'
                      AND attributes->>'progress' = 'true'
                      AND NULLIF(attributes->>'result_summary', '') IS NOT NULL
                    ORDER BY sequence_no
                    """
                ),
                {"execution_id": execution["id"]},
            )
        ).mappings().all()
        metadata = dict(execution["metadata"] or {})
        recommendation = self._recommendation(
            str(failed_operation.get("name", "action"))
        )
        packet = ContinuityPacket(
            task=str(metadata.get("task", "Continue the interrupted execution")),
            source_execution_id=execution["id"],
            source_provider=execution["active_provider"] or "custom",
            source_model=execution["active_model"] or execution["requested_model"],
            completed_work=[row["summary"] for row in completed_rows],
            failed_operation=failed_operation,
            reason_for_intervention=reason,
            recommended_action=recommendation,
            evidence=evidence,
            created_at=now,
        )
        packet_json = packet.model_dump(mode="json")
        content_hash = fingerprint(packet_json)
        checkpoint_id = UUID(
            str(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO control.continuity_checkpoints (
                                execution_id, policy_decision_id,
                                content_fingerprint, packet
                            ) VALUES (
                                :execution_id, :policy_decision_id,
                                :content_fingerprint, CAST(:packet AS jsonb)
                            )
                            RETURNING id
                            """
                        ),
                        {
                            "execution_id": execution["id"],
                            "policy_decision_id": policy_decision_id,
                            "content_fingerprint": content_hash,
                            "packet": json.dumps(packet_json),
                        },
                    )
                ).scalar_one()
            )
        )
        return checkpoint_id

    @staticmethod
    def _checkpoint_from_row(row) -> RuntimeCheckpoint | None:  # type: ignore[no-untyped-def]
        if row is None:
            return None
        return RuntimeCheckpoint(
            id=row["id"],
            execution_id=row["execution_id"],
            status=row["status"],
            content_fingerprint=row["content_fingerprint"],
            packet=ContinuityPacket.model_validate(row["packet"]),
            created_at=row["created_at"],
            consumed_at=row["consumed_at"],
        )

    @staticmethod
    def _result_summary(result: Any, requested_summary: str | None) -> str:
        if requested_summary:
            return str(sanitize_value(requested_summary))[:500]
        sanitized = sanitize_value(result)
        if isinstance(sanitized, dict):
            results = sanitized.get("results")
            if isinstance(results, list) and not results:
                return "No results returned"
        rendered = json.dumps(sanitized, ensure_ascii=True, sort_keys=True)
        return rendered[:500]

    @staticmethod
    def _recommendation(action_name: str) -> str:
        if "search" in action_name.lower():
            return "Broaden the query, change the source, or add a no-results exit condition."
        return "Change the action arguments or add an explicit no-progress exit condition."
