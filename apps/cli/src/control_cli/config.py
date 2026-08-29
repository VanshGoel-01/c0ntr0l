import os
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class CliConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CliConfig:
    api_url: str
    api_key: str

    @classmethod
    def from_environment(cls) -> "CliConfig":
        api_url = normalize_api_url(
            os.environ.get("CONTROL_API_URL", "http://127.0.0.1:8000")
        )
        api_key = os.environ.get("CONTROL_API_KEY", "").strip()
        if not 36 <= len(api_key) <= 64 or not api_key.startswith("ctl_"):
            raise CliConfigurationError(
                "CONTROL_API_KEY must be a valid project key beginning with ctl_"
            )
        return cls(api_url=api_url, api_key=api_key)


def normalize_api_url(value: str) -> str:
    candidate = value.strip()
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise CliConfigurationError("CONTROL_API_URL is malformed") from exc

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CliConfigurationError("CONTROL_API_URL must be an HTTP(S) URL")
    if parsed.username or parsed.password:
        raise CliConfigurationError("CONTROL_API_URL cannot contain credentials")
    if parsed.query or parsed.fragment:
        raise CliConfigurationError(
            "CONTROL_API_URL cannot contain query or fragment data"
        )
    if parsed.scheme == "http" and parsed.hostname.lower() not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise CliConfigurationError("Remote control APIs must use HTTPS")

    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    netloc = f"{host}:{port}" if port is not None else host
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, netloc, path, "", ""))
