#!/usr/bin/env python3
"""Run every check for backend and frontend. Standard library only, works on Windows and Linux.

Usage:
    python scripts/check.py            # all checks
    python scripts/check.py --fix      # apply formatting and safe lint fixes first
    python scripts/check.py backend    # only one side
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        sys.exit(f"error: `{name}` not found on PATH. See CLAUDE.md for setup instructions.")
    return path


def backend_steps(fix: bool) -> list[tuple[str, list[str]]]:
    uv = [_tool("uv"), "run", "--frozen"]
    paths = [".", "../scripts"]
    steps: list[tuple[str, list[str]]] = []
    if fix:
        steps += [
            ("backend: ruff fix", [*uv, "ruff", "check", "--fix", *paths]),
            ("backend: ruff format", [*uv, "ruff", "format", *paths]),
        ]
    steps += [
        ("backend: format", [*uv, "ruff", "format", "--check", *paths]),
        ("backend: lint", [*uv, "ruff", "check", *paths]),
        ("backend: types", [*uv, "mypy", "app", "tests", "../scripts"]),
        ("backend: tests", [*uv, "pytest", "-q"]),
    ]
    return steps


def frontend_steps(fix: bool) -> list[tuple[str, list[str]]]:
    npm = [_tool("npm"), "run", "--silent"]
    steps: list[tuple[str, list[str]]] = []
    if fix:
        steps.append(("frontend: prettier write", [*npm, "format"]))
    steps += [
        ("frontend: format", [*npm, "format:check"]),
        ("frontend: lint", [*npm, "lint"]),
        ("frontend: types", [*npm, "typecheck"]),
        ("frontend: tests", [*npm, "test"]),
        ("frontend: build", [*npm, "build"]),
    ]
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=["all", "backend", "frontend"], default="all")
    parser.add_argument("--fix", action="store_true", help="apply formatting fixes first")
    args = parser.parse_args()

    env = {**os.environ, "UV_PYTHON_PREFERENCE": "only-managed"}
    plan: list[tuple[str, list[str], Path]] = []
    if args.target in ("all", "backend"):
        plan += [(n, c, BACKEND) for n, c in backend_steps(args.fix)]
    if args.target in ("all", "frontend"):
        plan += [(n, c, FRONTEND) for n, c in frontend_steps(args.fix)]

    results: list[tuple[str, bool, float]] = []
    for name, cmd, cwd in plan:
        print(f"\n=== {name} ===", flush=True)
        started = time.monotonic()
        ok = subprocess.run(cmd, cwd=cwd, env=env, check=False).returncode == 0  # noqa: S603
        results.append((name, ok, time.monotonic() - started))

    print("\n=== summary ===")
    for name, ok, seconds in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  ({seconds:.1f}s)")
    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
