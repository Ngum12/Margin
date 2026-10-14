#!/usr/bin/env python3
"""Start the Marking Assistant with one command. Standard library only.

    python scripts/run.py           # production mode: build frontend if needed, serve it
    python scripts/run.py --dev     # development: FastAPI with reload + Vite dev server
    python scripts/run.py --rebuild # force a fresh frontend build first

Host and port come from MARGIN_HOST / MARGIN_PORT (or .env), defaulting to 127.0.0.1:8000.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        sys.exit(f"error: `{name}` not found on PATH. See CLAUDE.md for setup instructions.")
    return path


def _read_dotenv() -> dict[str, str]:
    values: dict[str, str] = {}
    dotenv = ROOT / ".env"
    if dotenv.is_file():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _frontend_is_stale() -> bool:
    index = FRONTEND / "dist" / "index.html"
    if not index.is_file():
        return True
    built = index.stat().st_mtime
    sources = [FRONTEND / "index.html", *(FRONTEND / "src").rglob("*")]
    return any(p.is_file() and p.stat().st_mtime > built for p in sources)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", action="store_true", help="reload + Vite dev server")
    parser.add_argument("--rebuild", action="store_true", help="force a frontend rebuild")
    args = parser.parse_args()

    env = {**_read_dotenv(), **os.environ, "UV_PYTHON_PREFERENCE": "only-managed"}
    host = env.get("MARGIN_HOST", "127.0.0.1")
    port = env.get("MARGIN_PORT", "8000")
    npm = _tool("npm")
    uvicorn = [
        _tool("uv"),
        "run",
        "--frozen",
        "uvicorn",
        "--factory",
        "app.main:app_factory",
        "--host",
        host,
        "--port",
        port,
    ]

    if not (FRONTEND / "node_modules").is_dir():
        subprocess.run([npm, "ci"], cwd=FRONTEND, check=True)  # noqa: S603

    if args.dev:
        env.setdefault("MARGIN_ENV", "development")
        env["MARGIN_BACKEND_URL"] = f"http://{host}:{port}"
        vite = subprocess.Popen([npm, "run", "dev"], cwd=FRONTEND, env=env)  # noqa: S603
        try:
            dev = subprocess.run([*uvicorn, "--reload"], cwd=BACKEND, env=env, check=False)  # noqa: S603
            return dev.returncode
        finally:
            vite.terminate()

    if args.rebuild or _frontend_is_stale():
        print("Building frontend...", flush=True)
        subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)  # noqa: S603

    print(f"Marking Assistant: http://{host}:{port}", flush=True)
    return subprocess.run(uvicorn, cwd=BACKEND, env=env, check=False).returncode  # noqa: S603


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
