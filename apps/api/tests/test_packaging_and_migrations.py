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


def test_budget_reservations_track_claimed_provider_requests() -> None:
    reservation_schema = (
        ROOT / "migrations" / "postgres" / "080_budget_reservation_claims.sql"
    ).read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS claimed_requests" in reservation_schema


def test_recovery_attempts_support_pre_provider_budget_blocks() -> None:
    admission_schema = (
        ROOT / "migrations" / "postgres" / "090_recovery_budget_admission.sql"
    ).read_text(encoding="utf-8")

    assert "'blocked'" in admission_schema
    assert "recovery_attempts_status_check" in admission_schema


def test_model_policies_are_project_scoped_and_auditable() -> None:
    policy_schema = (
        ROOT / "migrations" / "postgres" / "100_model_policies.sql"
    ).read_text(encoding="utf-8")
    repository = (
        ROOT / "apps" / "api" / "app" / "repositories" / "model_policies.py"
    ).read_text(encoding="utf-8")

    assert "UNIQUE (project_id, provider, model)" in policy_schema
    assert "CHECK (mode IN ('observe', 'warn', 'block'))" in policy_schema
    assert "'model_policy.updated'" in repository
