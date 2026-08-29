from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[3]


def test_httpx_is_an_api_runtime_dependency() -> None:
    with (ROOT / "apps" / "api" / "pyproject.toml").open("rb") as file:
        project = tomllib.load(file)["project"]

    assert any(dependency.startswith("httpx") for dependency in project["dependencies"])


def test_request_ids_are_correlation_values_not_global_unique_keys() -> None:
    execution_schema = (
        ROOT / "migrations" / "postgres" / "020_executions_and_traces.sql"
    ).read_text(encoding="utf-8")
    compatibility_migration = (
        ROOT / "migrations" / "postgres" / "060_execution_request_ids.sql"
    ).read_text(encoding="utf-8")

    assert "request_id text NOT NULL UNIQUE" not in execution_schema
    assert "DROP CONSTRAINT IF EXISTS executions_request_id_key" in (
        compatibility_migration
    )
    assert "ON control.executions (project_id, request_id)" in compatibility_migration


def test_runtime_recovery_schema_preserves_checkpoint_and_audit_history() -> None:
    recovery_schema = (
        ROOT / "migrations" / "postgres" / "070_runtime_recovery.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS control.continuity_checkpoints" in recovery_schema
    assert "CREATE TABLE IF NOT EXISTS control.recovery_attempts" in recovery_schema
    assert "raw provider context are forbidden" in recovery_schema
