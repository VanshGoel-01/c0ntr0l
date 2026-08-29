"""Apply the ordered PostgreSQL schema files to the local Docker database."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT / ".env"
COMPOSE_FILE = ROOT / "deploy" / "docker-compose.yml"
MIGRATIONS_DIR = ROOT / "migrations" / "postgres"


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


def apply_file(path: Path, env_file: Path) -> None:
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
        "psql",
        "-X",
        "-1",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        required("POSTGRES_USER"),
        "-d",
        required("POSTGRES_DB"),
    ]
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            input=path.read_text(encoding="utf-8"),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Docker CLI is not installed or is not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Timed out while applying {path.name}") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Failed to apply {path.name}: {detail}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply c0ntr0l PostgreSQL schema files in filename order."
    )
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        env_file = args.env_file.resolve()
        load_env(env_file)
        migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
        if not migrations:
            raise RuntimeError(f"No SQL files found in {MIGRATIONS_DIR}")

        for migration in migrations:
            apply_file(migration, env_file)
            print(f"[PASS] Applied {migration.name}")
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print("[PASS] PostgreSQL schema is up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
