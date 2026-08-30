import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from control_schemas import (
    ExecutionDetail,
    ExecutionSummary,
    IncidentContext,
    RuntimeCancellationResult,
    RuntimeIntervention,
    RuntimeRecoveryResult,
    WorkspaceContext,
)
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table
from rich.text import Text


def write_json(console: Console, value: Any) -> None:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    elif isinstance(value, list):
        value = [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item
            for item in value
        ]
    console.print_json(json.dumps(value, default=str))


def status_table(
    console: Console, health: dict[str, Any], workspace: WorkspaceContext
) -> None:
    table = Table(title="Control plane", show_header=False, box=None)
    table.add_column("Field", style="dim")
    table.add_column("Value")
    table.add_row("Status", _state(str(health.get("status", "unknown"))))
    table.add_row("Organization", workspace.organization_name)
    table.add_row("Project", f"{workspace.project_name} ({workspace.project_slug})")
    table.add_row("Applications", str(len(workspace.applications)))
    table.add_row("Requests (24h)", str(workspace.requests_24h))
    table.add_row("Tokens (24h)", f"{workspace.tokens_24h:,}")
    table.add_row("Cost (24h)", _money(workspace.cost_24h))
    dependencies = health.get("dependencies")
    if isinstance(dependencies, dict):
        for name, value in dependencies.items():
            state = value.get("status", "unknown") if isinstance(value, dict) else value
            table.add_row(f"Dependency: {name}", _state(str(state)))
    console.print(table)


def executions_table(console: Console, executions: list[ExecutionSummary]) -> None:
    if console.width < 120:
        _compact_executions(console, executions)
        return

    table = Table(title=f"Executions ({len(executions)})")
    table.add_column("Trace", no_wrap=True)
    table.add_column("Application")
    table.add_column("Model")
    table.add_column("Status")
    table.add_column("Tokens", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Started", no_wrap=True)
    for execution in executions:
        table.add_row(
            execution.request_id or str(execution.id)[:8],
            execution.application_name or "-",
            execution.active_model or execution.requested_model,
            _state(execution.status),
            f"{execution.total_tokens:,}",
            _duration(execution.duration_ms),
            _time(execution.started_at),
        )
    console.print(table)


def _compact_executions(console: Console, executions: list[ExecutionSummary]) -> None:
    console.print(f"[bold]Executions ({len(executions)})[/bold]")
    for index, execution in enumerate(executions):
        record = Table.grid(padding=(0, 1))
        record.add_column(style="dim", no_wrap=True)
        record.add_column(overflow="fold")
        record.add_row("Execution", Text(str(execution.id), style="bold"))
        record.add_row("Trace", execution.request_id or "-")
        record.add_row("Application", execution.application_name or "-")
        record.add_row("Model", execution.active_model or execution.requested_model)
        record.add_row("Status", _state(execution.status))
        record.add_row("Tokens", f"{execution.total_tokens:,}")
        record.add_row("Duration", _duration(execution.duration_ms))
        record.add_row("Started", _time(execution.started_at))
        console.print(record)
        if index < len(executions) - 1:
            console.print()


def execution_detail(
    console: Console,
    execution: ExecutionDetail,
    intervention: RuntimeIntervention | None,
) -> None:
    summary = Table(title="Execution", show_header=False, box=None)
    summary.add_column("Field", style="dim")
    summary.add_column("Value")
    summary.add_row("Execution ID", str(execution.id))
    summary.add_row("Trace ID", execution.request_id or "-")
    summary.add_row("Project", execution.project_name or "-")
    summary.add_row("Application", execution.application_name or "-")
    summary.add_row("Provider", execution.active_provider or "-")
    summary.add_row("Model", execution.active_model or execution.requested_model)
    summary.add_row("Status", _state(execution.status))
    summary.add_row("Tokens", f"{execution.total_tokens:,}")
    summary.add_row("Cost", _money(execution.total_cost))
    summary.add_row("Duration", _duration(execution.duration_ms))
    if intervention is not None:
        summary.add_row("Intervention", intervention.reason)
        summary.add_row("Decision", _state(intervention.outcome))
        if intervention.checkpoint is not None:
            summary.add_row("Checkpoint", str(intervention.checkpoint.id))
    console.print(summary)

    if console.width < 120:
        _compact_spans(console, execution)
        return

    spans = Table(title=f"Spans ({len(execution.spans)})")
    spans.add_column("#", justify="right")
    spans.add_column("Kind")
    spans.add_column("Name")
    spans.add_column("Status")
    spans.add_column("Duration", justify="right")
    spans.add_column("Error")
    for span in execution.spans:
        spans.add_row(
            str(span.sequence_no),
            span.kind,
            span.name,
            _state(span.status),
            _duration(span.duration_ms),
            span.error_code or "-",
        )
    console.print(spans)


def _compact_spans(console: Console, execution: ExecutionDetail) -> None:
    console.print(f"[bold]Spans ({len(execution.spans)})[/bold]")
    for index, span in enumerate(execution.spans):
        record = Table.grid(padding=(0, 1))
        record.add_column(style="dim", no_wrap=True)
        record.add_column(overflow="fold")
        record.add_row("Span", str(span.id))
        record.add_row("Sequence", str(span.sequence_no))
        record.add_row("Kind", span.kind)
        record.add_row("Name", span.name)
        record.add_row("Status", _state(span.status))
        record.add_row("Duration", _duration(span.duration_ms))
        record.add_row("Error", span.error_code or "-")
        console.print(record)
        if index < len(execution.spans) - 1:
            console.print()


def incidents_table(console: Console, incidents: list[IncidentContext]) -> None:
    if console.width < 120:
        _compact_incidents(console, incidents)
        return

    table = Table(title=f"Incidents ({len(incidents)})")
    table.add_column("ID", no_wrap=True)
    table.add_column("Severity")
    table.add_column("Type")
    table.add_column("Application")
    table.add_column("Description")
    table.add_column("Status")
    table.add_column("Created", no_wrap=True)
    for incident in incidents:
        table.add_row(
            str(incident.id)[:8],
            _state(incident.severity),
            incident.incident_type.replace("_", " "),
            incident.application_name,
            incident.title,
            _state(incident.status.value),
            _time(incident.created_at),
        )
    console.print(table)


def _compact_incidents(console: Console, incidents: list[IncidentContext]) -> None:
    console.print(f"[bold]Incidents ({len(incidents)})[/bold]")
    for index, incident in enumerate(incidents):
        record = Table.grid(padding=(0, 1))
        record.add_column(style="dim", no_wrap=True)
        record.add_column(overflow="fold")
        record.add_row("Incident", Text(str(incident.id), style="bold"))
        record.add_row("Execution", str(incident.execution_id))
        record.add_row("Severity", _state(incident.severity))
        record.add_row("Type", incident.incident_type.replace("_", " "))
        record.add_row("Application", incident.application_name)
        record.add_row("Description", incident.title)
        record.add_row("Status", _state(incident.status.value))
        record.add_row("Created", _time(incident.created_at))
        console.print(record)
        if index < len(incidents) - 1:
            console.print()


def incident_result(console: Console, incident: IncidentContext) -> None:
    console.print(
        f"Incident [bold]{incident.id}[/bold] is now {_state(incident.status.value)}"
    )


def cancellation_result(console: Console, result: RuntimeCancellationResult) -> None:
    console.print(
        f"Execution [bold]{result.execution_id}[/bold] is {_state(result.status)}"
    )
    if result.checkpoint_id is not None:
        console.print(f"Checkpoint: [bold]{result.checkpoint_id}[/bold]")


def recovery_result(console: Console, result: RuntimeRecoveryResult) -> None:
    table = Table(title="Recovery", show_header=False, box=None)
    table.add_column("Field", style="dim")
    table.add_column("Value")
    table.add_row("Source execution", str(result.source_execution_id))
    table.add_row("Strategy", result.strategy.value)
    table.add_row("Status", _state(result.status))
    table.add_row("Resumed execution", str(result.resumed_execution_id or "-"))
    table.add_row(
        "Target", f"{result.target_provider or '-'} / {result.target_model or '-'}"
    )
    table.add_row("Message", result.message)
    console.print(table)


def _state(value: str) -> Text:
    normalized = value.lower()
    color = {
        "healthy": "green",
        "ok": "green",
        "operational": "green",
        "completed": "green",
        "resolved": "green",
        "running": "cyan",
        "prepared": "cyan",
        "acknowledged": "yellow",
        "warning": "yellow",
        "warn": "yellow",
        "open": "red",
        "critical": "red",
        "failed": "red",
        "blocked": "red",
        "cancelled": "red",
        "block": "red",
        "cancel": "red",
    }.get(normalized, "white")
    return Text(value, style=color)


def _money(value: Decimal) -> str:
    return f"${value:,.4f}"


def _duration(value: int | None) -> str:
    if value is None:
        return "-"
    if value < 1_000:
        return f"{value}ms"
    return f"{value / 1_000:.2f}s"


def _time(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")
