from collections.abc import Callable
from typing import Annotated, TypeVar
from uuid import UUID

import typer
from control_schemas import IncidentStatus, RecoveryStrategy, RuntimeRecoveryRequest
from pydantic import ValidationError
from rich.console import Console

from control_cli import __version__
from control_cli.client import ControlApiError, ControlClient
from control_cli.config import CliConfig, CliConfigurationError
from control_cli.render import (
    cancellation_result,
    execution_detail,
    executions_table,
    incident_result,
    incidents_table,
    recovery_result,
    status_table,
    write_json,
)

app = typer.Typer(
    add_completion=False,
    help="Inspect and control c0ntr0l AI executions.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
console = Console()
error_console = Console(stderr=True)
Result = TypeVar("Result")


class OutputState:
    def __init__(self, json_output: bool) -> None:
        self.json_output = json_output


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"c0ntr0l {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    context: typer.Context,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Write machine-readable JSON."),
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show the CLI version.",
        ),
    ] = False,
) -> None:
    del version
    context.obj = OutputState(json_output)


@app.command()
def status(context: typer.Context) -> None:
    """Show API health, project identity, and 24-hour usage."""

    health, workspace = _call(lambda client: (client.health(), client.workspace()))
    if _json(context):
        write_json(
            console,
            {"health": health, "workspace": workspace.model_dump(mode="json")},
        )
    else:
        status_table(console, health, workspace)


@app.command()
def runs(
    context: typer.Context,
    limit: Annotated[int, typer.Option(min=1, max=100)] = 20,
) -> None:
    """List recent project executions."""

    result = _call(lambda client: client.executions(limit))
    write_json(console, result) if _json(context) else executions_table(console, result)


@app.command("run")
def show_run(context: typer.Context, execution_id: UUID) -> None:
    """Show one execution, its spans, usage, and intervention."""

    detail, intervention = _call(
        lambda client: (
            client.execution(execution_id),
            client.intervention(execution_id),
        )
    )
    if _json(context):
        write_json(
            console,
            {
                "execution": detail.model_dump(mode="json"),
                "intervention": (
                    intervention.model_dump(mode="json")
                    if intervention is not None
                    else None
                ),
            },
        )
    else:
        execution_detail(console, detail, intervention)


@app.command()
def incidents(
    context: typer.Context,
    status: Annotated[IncidentStatus | None, typer.Option()] = None,
    limit: Annotated[int, typer.Option(min=1, max=500)] = 100,
) -> None:
    """List project incidents, optionally filtered by status."""

    result = _call(lambda client: client.incidents(limit, status))
    write_json(console, result) if _json(context) else incidents_table(console, result)


@app.command("incident")
def update_incident(
    context: typer.Context,
    incident_id: UUID,
    status: Annotated[IncidentStatus, typer.Option("--set-status")],
) -> None:
    """Acknowledge, resolve, or reopen an incident."""

    result = _call(lambda client: client.update_incident(incident_id, status))
    write_json(console, result) if _json(context) else incident_result(console, result)


@app.command()
def cancel(
    context: typer.Context,
    execution_id: UUID,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip the confirmation prompt."),
    ] = False,
) -> None:
    """Cancel a running execution and preserve its checkpoint."""

    if not yes and not typer.confirm(f"Cancel execution {execution_id}?"):
        raise typer.Abort()
    result = _call(lambda client: client.cancel(execution_id))
    write_json(console, result) if _json(context) else cancellation_result(
        console, result
    )


@app.command()
def recover(
    context: typer.Context,
    execution_id: UUID,
    strategy: Annotated[RecoveryStrategy, typer.Option()],
    query: Annotated[str | None, typer.Option(help="Modified retry query.")] = None,
    provider: Annotated[str | None, typer.Option(help="Handoff provider.")] = None,
    model: Annotated[str | None, typer.Option(help="Handoff model.")] = None,
) -> None:
    """Resume a checkpoint using an approved recovery strategy."""

    clean_query = query.strip() if query is not None else None
    clean_provider = provider.strip() if provider is not None else None
    clean_model = model.strip() if model is not None else None
    try:
        request = RuntimeRecoveryRequest(
            strategy=strategy,
            modified_arguments={"query": clean_query} if clean_query else None,
            target_provider=clean_provider,
            target_model=clean_model,
        )
    except ValidationError as exc:
        error_console.print(
            f"[red]Invalid recovery request:[/red] {exc.errors()[0]['msg']}"
        )
        raise typer.Exit(code=2) from exc
    result = _call(lambda client: client.recover(execution_id, request))
    write_json(console, result) if _json(context) else recovery_result(console, result)


def _call(operation: Callable[[ControlClient], Result]) -> Result:
    try:
        config = CliConfig.from_environment()
        with ControlClient(config) as client:
            return operation(client)
    except (CliConfigurationError, ControlApiError) as exc:
        error_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


def _json(context: typer.Context) -> bool:
    state = context.obj
    return isinstance(state, OutputState) and state.json_output


def run() -> None:
    app()


if __name__ == "__main__":
    run()
