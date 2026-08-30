from datetime import UTC, datetime
from io import StringIO
from uuid import UUID

from control_cli.render import execution_detail, executions_table, incidents_table
from control_schemas import ExecutionDetail, ExecutionSummary, IncidentContext
from rich.console import Console

EXECUTION_ID = UUID("00000000-0000-0000-0000-000000000010")
SPAN_ID = UUID("00000000-0000-0000-0000-000000000011")
INCIDENT_ID = UUID("00000000-0000-0000-0000-000000000012")


def test_narrow_execution_output_keeps_actionable_identifiers() -> None:
    output = StringIO()
    console = Console(
        file=output,
        width=80,
        color_system=None,
        force_terminal=False,
    )
    execution = ExecutionSummary.model_validate(
        {
            "id": str(EXECUTION_ID),
            "request_id": "run_2152ad3543ef44868c1a4916c318fbca",
            "project_id": None,
            "project_name": "Gateway Demo",
            "application_id": None,
            "application_name": "Research Agent",
            "agent_name": None,
            "status": "blocked",
            "requested_model": "mock-gpt",
            "active_provider": "mock",
            "active_model": "mock-gpt",
            "is_streaming": False,
            "input_fingerprint": None,
            "output_fingerprint": None,
            "started_at": datetime(2026, 8, 30, tzinfo=UTC),
            "completed_at": datetime(2026, 8, 30, tzinfo=UTC),
            "duration_ms": 125,
            "span_count": 3,
            "total_tokens": 1200,
            "total_cost": "0",
            "final_reason": "policy_block",
            "error_code": "model_policy_block",
            "metadata": {},
        }
    )

    executions_table(console, [execution])

    rendered = output.getvalue()
    assert str(EXECUTION_ID) in rendered
    assert "run_2152ad3543ef44868c1a4916c318fbca" in rendered
    assert "Research Agent" in rendered
    assert "mock-gpt" in rendered
    assert "blocked" in rendered
    assert "1,200" in rendered
    assert "\ufffd" not in rendered


def test_narrow_trace_output_does_not_truncate_span_evidence() -> None:
    output = StringIO()
    console = Console(file=output, width=80, color_system=None, force_terminal=False)
    execution = ExecutionDetail.model_validate(
        {
            "id": str(EXECUTION_ID),
            "request_id": "req_trace",
            "project_id": None,
            "project_name": "Gateway Demo",
            "application_id": None,
            "application_name": "Research Agent",
            "agent_name": None,
            "status": "blocked",
            "requested_model": "mock-gpt",
            "active_provider": "mock",
            "active_model": "mock-gpt",
            "is_streaming": False,
            "input_fingerprint": None,
            "output_fingerprint": None,
            "started_at": datetime(2026, 8, 30, tzinfo=UTC),
            "completed_at": datetime(2026, 8, 30, tzinfo=UTC),
            "duration_ms": 125,
            "span_count": 1,
            "total_tokens": 0,
            "total_cost": "0",
            "final_reason": "policy_block",
            "error_code": "model_policy_block",
            "metadata": {},
            "spans": [
                {
                    "id": str(SPAN_ID),
                    "parent_span_id": None,
                    "sequence_no": 1,
                    "kind": "provider",
                    "name": "mock.chat.completion.policy_skipped",
                    "tool_name": None,
                    "status": "blocked",
                    "duration_ms": 0,
                    "error_code": "model_policy_block",
                    "started_at": datetime(2026, 8, 30, tzinfo=UTC),
                    "completed_at": datetime(2026, 8, 30, tzinfo=UTC),
                    "attributes": {},
                }
            ],
            "usage": [],
        }
    )

    execution_detail(console, execution, None)

    rendered = output.getvalue()
    assert str(SPAN_ID) in rendered
    assert "mock.chat.completion.policy_skipped" in rendered
    assert "model_policy_block" in rendered
    assert "\ufffd" not in rendered


def test_narrow_incident_output_keeps_full_actionable_ids() -> None:
    output = StringIO()
    console = Console(file=output, width=80, color_system=None, force_terminal=False)
    incident = IncidentContext(
        id=INCIDENT_ID,
        execution_id=EXECUTION_ID,
        trace_id="req_trace",
        application_name="Research Agent",
        provider="mock",
        model="mock-gpt",
        incident_type="manual_intervention",
        severity="critical",
        status="open",
        title="Model call blocked before provider invocation",
        evidence={"reason": "model policy"},
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
        acknowledged_at=None,
        resolved_at=None,
    )

    incidents_table(console, [incident])

    rendered = output.getvalue()
    assert str(INCIDENT_ID) in rendered
    assert str(EXECUTION_ID) in rendered
    assert "Model call blocked before provider invocation" in rendered
    assert "\ufffd" not in rendered
