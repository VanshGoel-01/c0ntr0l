"""Verify the local PostgreSQL and Redis development services.

This script uses only the Python standard library so it can run before the API
dependencies are installed. It never prints passwords or secret values.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT / ".env"
COMPOSE_FILE = ROOT / "deploy" / "docker-compose.yml"
EXPECTED_RELATIONS = (
    "control.organizations",
    "control.users",
    "control.organization_members",
    "control.projects",
    "control.applications",
    "control.agents",
    "control.project_api_keys",
    "control.executions",
    "control.spans",
    "control.provider_attempts",
    "control.usage_records",
    "control.budget_policies",
    "control.budget_reservations",
    "control.budget_ledger",
    "control.loop_observations",
    "control.policy_decisions",
    "control.incidents",
    "control.provider_handoffs",
    "audit.events",
)


def load_env(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"Environment file not found: {path}. Copy .env.example to .env first."
        )

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Required environment variable is missing: {name}")
    return value


def check_tcp(name: str, host: str, port: int, timeout: float) -> None:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return
    except OSError as exc:
        raise RuntimeError(f"{name} is unreachable at {host}:{port}: {exc}") from exc


def check_postgres(host: str, port: int, timeout: float, env_file: Path) -> str:
    check_tcp("PostgreSQL", host, port, timeout)

    command = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(COMPOSE_FILE),
        "exec",
        "-T",
        "postgres",
        "pg_isready",
        "-U",
        required("POSTGRES_USER"),
        "-d",
        required("POSTGRES_DB"),
    ]
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=max(5.0, timeout * 2),
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Docker CLI is not installed or is not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("PostgreSQL readiness check timed out") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"PostgreSQL is reachable but not ready: {detail}")

    expected_values = ",".join(f"('{name}')" for name in EXPECTED_RELATIONS)
    schema_query = (
        "SELECT name FROM (VALUES "
        f"{expected_values}"
        ") AS expected(name) "
        "WHERE to_regclass(name) IS NULL ORDER BY name;"
    )
    schema_command = command[:-5] + [
        "psql",
        "-X",
        "-A",
        "-t",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        required("POSTGRES_USER"),
        "-d",
        required("POSTGRES_DB"),
        "-c",
        schema_query,
    ]
    try:
        schema_result = subprocess.run(
            schema_command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=max(5.0, timeout * 2),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("PostgreSQL schema check timed out") from exc

    if schema_result.returncode != 0:
        detail = (schema_result.stderr or schema_result.stdout).strip()
        raise RuntimeError(f"PostgreSQL schema check failed: {detail}")

    missing = [line for line in schema_result.stdout.splitlines() if line.strip()]
    if missing:
        raise RuntimeError(
            "PostgreSQL is missing schema objects: "
            f"{', '.join(missing)}. Run scripts/apply_postgres_schema.py."
        )

    readiness = result.stdout.strip() or "accepting connections"
    return f"{readiness}; {len(EXPECTED_RELATIONS)} schema tables present"


def check_redis(host: str, port: int, timeout: float) -> str:
    request = b"*1\r\n$4\r\nPING\r\n"
    try:
        with socket.create_connection((host, port), timeout=timeout) as connection:
            connection.settimeout(timeout)
            connection.sendall(request)
            response = connection.recv(64)
    except OSError as exc:
        raise RuntimeError(f"Redis is unreachable at {host}:{port}: {exc}") from exc

    if not response.startswith(b"+PONG"):
        raise RuntimeError(f"Redis returned an unexpected response: {response!r}")
    return "PONG"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check local c0ntr0l PostgreSQL and Redis services."
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help="Environment file to load (default: .env)",
    )
    parser.add_argument("--timeout", type=float, default=3.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        env_file = args.env_file.resolve()
        load_env(env_file)

        postgres_host = required("POSTGRES_HOST")
        postgres_port = int(required("POSTGRES_PORT"))
        redis_host = required("REDIS_HOST")
        redis_port = int(required("REDIS_PORT"))

        postgres_result = check_postgres(
            postgres_host, postgres_port, args.timeout, env_file
        )
        print(f"[PASS] PostgreSQL: {postgres_result}")

        redis_result = check_redis(redis_host, redis_port, args.timeout)
        print(f"[PASS] Redis: {redis_result}")
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print("[PASS] Infrastructure is ready for API development")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
