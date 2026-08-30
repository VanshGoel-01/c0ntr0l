import pytest
from control_cli.config import CliConfig, CliConfigurationError, normalize_api_url

KEY = "ctl_" + "a" * 40


def test_config_reads_project_key_without_putting_it_in_url(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CONTROL_API_URL", "http://localhost:8000/")
    monkeypatch.setenv("CONTROL_API_KEY", KEY)

    config = CliConfig.from_environment()

    assert config.api_url == "http://localhost:8000"
    assert config.api_key == KEY
    assert KEY not in config.api_url


@pytest.mark.parametrize(
    "url",
    [
        "http://control.example.com",
        "ftp://localhost:8000",
        "https://user:password@control.example.com",
        "https://control.example.com?token=secret",
        "not-a-url",
    ],
)
def test_config_rejects_unsafe_api_urls(url: str) -> None:
    with pytest.raises(CliConfigurationError):
        normalize_api_url(url)


def test_config_accepts_https_remote_api() -> None:
    assert normalize_api_url("https://control.example.com/") == (
        "https://control.example.com"
    )


def test_config_requires_project_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("CONTROL_API_KEY", raising=False)

    with pytest.raises(CliConfigurationError):
        CliConfig.from_environment()
