import control_cli.main as main_module
from typer.testing import CliRunner

runner = CliRunner()


def test_help_lists_operational_commands() -> None:
    result = runner.invoke(main_module.app, ["--help"])

    assert result.exit_code == 0
    assert "runs" in result.stdout
    assert "incidents" in result.stdout
    assert "cancel" in result.stdout
    assert "recover" in result.stdout


def test_version_does_not_require_configuration() -> None:
    result = runner.invoke(main_module.app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "c0ntr0l 0.1.0"


def test_status_fails_cleanly_without_project_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("CONTROL_API_KEY", raising=False)

    result = runner.invoke(main_module.app, ["status"])

    assert result.exit_code == 1
    assert "CONTROL_API_KEY" in result.stderr
    assert "Traceback" not in result.stderr


def test_cancel_requires_confirmation_before_api_call(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    called = False

    def forbidden_call(operation):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True
        raise AssertionError("API must not be called")

    monkeypatch.setattr(main_module, "_call", forbidden_call)
    result = runner.invoke(
        main_module.app,
        ["cancel", "00000000-0000-0000-0000-000000000001"],
        input="n\n",
    )

    assert result.exit_code == 1
    assert called is False


def test_invalid_handoff_is_rejected_before_api_call(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    called = False

    def forbidden_call(operation):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True
        raise AssertionError("API must not be called")

    monkeypatch.setattr(main_module, "_call", forbidden_call)
    result = runner.invoke(
        main_module.app,
        [
            "recover",
            "00000000-0000-0000-0000-000000000001",
            "--strategy",
            "model_handoff",
        ],
    )

    assert result.exit_code == 2
    assert "target_provider and target_model" in result.stderr
    assert "required for model_handoff" in result.stderr
    assert called is False
