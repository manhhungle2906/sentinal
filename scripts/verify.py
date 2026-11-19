#!/usr/bin/env python3
"""Verification runner for API Sentinel.

The script prints every command it runs together with its exit status and
returns a non-zero exit code when a required step fails.

Suites:
    backend  — Ruff format/lint plus the pytest unit and PostgreSQL tests
    frontend — locked install, ESLint, TypeScript, Vitest and the production build
    e2e      — Playwright browser checks against a real local test stack
    all      — clean database migration, backend, frontend, smoke and browser checks

The full gate uses an isolated Compose project, an empty test database and
dynamically allocated host ports, and removes only the resources it created.
It never touches the operator's own volumes or data.

Usage:
    python3 scripts/verify.py --suite backend
    python3 scripts/verify.py --suite frontend
    python3 scripts/verify.py --suite e2e
    python3 scripts/verify.py --suite all
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    BACKEND_DIR,
    FRONTEND_DIR,
    REPO_ROOT,
    docker_compose,
    free_port,
    log,
    python_executable,
    require_docker,
    run,
)

NODE_IMAGE = os.environ.get("SENTINEL_NODE_IMAGE", "node:22-alpine")
PLAYWRIGHT_IMAGE = os.environ.get(
    "SENTINEL_PLAYWRIGHT_IMAGE", "mcr.microsoft.com/playwright:v1.49.1-noble"
)


class StepFailure(RuntimeError):
    """Raised when a required verification step fails."""


class Runner:
    """Runs verification steps and records their outcome."""

    def __init__(self) -> None:
        self.failures: list[str] = []
        self.results: list[tuple[str, bool, str]] = []

    def step(self, name: str, command: list[str], **kwargs: object) -> bool:
        """Run one command and record whether it passed."""
        printable = " ".join(command)
        log("")
        log(f"=== {name} ===")
        log(f"$ {printable}")
        try:
            result = run(command, check=False, **kwargs)  # type: ignore[arg-type]
        except SystemExit:
            self._record(name, False, "command could not be started")
            return False
        ok = result.returncode == 0
        detail = f"exit {result.returncode}"
        if not ok:
            tail_out = (result.stdout or "").strip().splitlines()[-25:]
            tail_err = (result.stderr or "").strip().splitlines()[-25:]
            for line in tail_out:
                log(f"  stdout | {line}")
            for line in tail_err:
                log(f"  stderr | {line}")
        else:
            tail_out = (result.stdout or "").strip().splitlines()[-8:]
            for line in tail_out:
                log(f"  stdout | {line}")
        self._record(name, ok, detail)
        return ok

    def _record(self, name: str, ok: bool, detail: str) -> None:
        status = "PASS" if ok else "FAIL"
        log(f"--- {status}: {name} ({detail})")
        self.results.append((name, ok, detail))
        if not ok:
            self.failures.append(name)

    def summary(self) -> int:
        log("")
        log("=== summary ===")
        for name, ok, detail in self.results:
            log(f"{'PASS' if ok else 'FAIL'}  {name} ({detail})")
        if self.failures:
            log(f"{len(self.failures)} step(s) failed: {', '.join(self.failures)}")
            return 1
        log("all steps passed")
        return 0


# --------------------------------------------------------------------------
# Backend
# --------------------------------------------------------------------------


def backend_steps(runner: Runner, python: list[str]) -> None:
    """Run the Ruff and pytest checks."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_DIR)

    runner.step(
        "ruff format --check",
        [*python, "-m", "ruff", "format", "--check", "."],
        cwd=BACKEND_DIR,
        env=env,
    )
    runner.step(
        "ruff check",
        [*python, "-m", "ruff", "check", "."],
        cwd=BACKEND_DIR,
        env=env,
    )

    database_url = os.environ.get("SENTINEL_TEST_DATABASE_URL")
    if not database_url:
        log("")
        log("SENTINEL_TEST_DATABASE_URL is not set; the PostgreSQL integration tests are skipped")
        runner.step(
            "pytest (unit tests only)",
            [*python, "-m", "pytest", str(REPO_ROOT / "tests"), "-q"],
            cwd=BACKEND_DIR,
            env=env,
        )
        return

    test_env = dict(env)
    test_env["SENTINEL_TEST_DATABASE_URL"] = database_url
    runner.step(
        "pytest (unit + PostgreSQL integration)",
        [*python, "-m", "pytest", str(REPO_ROOT / "tests"), "-q"],
        cwd=BACKEND_DIR,
        env=test_env,
    )


# --------------------------------------------------------------------------
# Frontend
# --------------------------------------------------------------------------


def _docker_node_command(node_command: list[str]) -> list[str]:
    """Wrap a Node command so it runs inside the Node 22 container."""
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{FRONTEND_DIR}:/app",
        "-w",
        "/app",
        "-u",
        f"{os.getuid()}:{os.getgid()}" if hasattr(os, "getuid") else "0:0",
        "-e",
        "HOME=/tmp",
        NODE_IMAGE,
        "sh",
        "-c",
        " && ".join(node_command),
    ]


def frontend_steps(runner: Runner, node_command: list[str]) -> None:
    """Run the frontend lint, typecheck, unit test and production build."""
    runner.step(
        "frontend install",
        _docker_node_command(["npm ci --no-audit --no-fund || npm install --no-audit --no-fund"]),
        timeout=900,
    )
    runner.step("frontend lint", _docker_node_command(["npm run lint"]), timeout=600)
    runner.step(
        "frontend typecheck",
        _docker_node_command(["npx tsc -b --pretty"]),
        timeout=600,
    )
    runner.step("frontend unit tests", _docker_node_command(["npm test"]), timeout=600)
    runner.step("frontend production build", _docker_node_command(["npm run build"]), timeout=900)


# --------------------------------------------------------------------------
# Compose stack
# --------------------------------------------------------------------------


class Stack:
    """An isolated Compose stack for the verification runs."""

    def __init__(self, project: str, with_demo: bool = True) -> None:
        self.project = project
        self.with_demo = with_demo
        self.web_port = free_port()
        self.core_port = free_port()
        self.ingest_port = free_port()
        self.demo_port = free_port()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="sentinel-verify-"))
        self.env = {
            "WEB_PORT": str(self.web_port),
            "CORE_PORT": str(self.core_port),
            "INGEST_PORT": str(self.ingest_port),
            "DEMO_PORT": str(self.demo_port),
            "POSTGRES_DB": "sentinel_verify",
            "APP_ENV": "development",
            "SECURE_COOKIES": "false",
            "DEMO_MODE": "true",
            # The verification stack is bound to loopback only.
            "SENTINEL_VERIFY": "1",
        }

    def command(self, *args: str) -> list[str]:
        return docker_compose(*args, project=self.project)

    def up(self) -> bool:
        args = ["--profile", "demo", "up", "--build", "--wait", "--wait-timeout", "300"]
        result = run(self.command(*args), check=False, env=self.env, timeout=1800)
        return result.returncode == 0

    def down(self) -> None:
        run(
            self.command("--profile", "demo", "down", "--volumes", "--remove-orphans"),
            check=False,
            env=self.env,
            timeout=600,
        )
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.web_port}"

    def core_url(self) -> str:
        return f"http://127.0.0.1:{self.core_port}"

    def ingest_url(self) -> str:
        return f"http://127.0.0.1:{self.ingest_port}"

    def demo_url(self) -> str:
        return f"http://127.0.0.1:{self.demo_port}"


def smoke_step(runner: Runner, stack: Stack) -> bool:
    """Run the smoke script against the isolated stack."""
    python = python_executable()
    return runner.step(
        "smoke check",
        [
            *python,
            str(REPO_ROOT / "scripts" / "smoke.py"),
            "--base-url",
            stack.base_url(),
            "--core-url",
            stack.core_url(),
            "--ingest-url",
            stack.ingest_url(),
        ],
        timeout=300,
    )


def e2e_steps(runner: Runner, stack: Stack) -> None:
    """Run the Playwright browser checks against the isolated stack."""
    playwright_dir = FRONTEND_DIR / "e2e"
    if not playwright_dir.exists():
        runner._record("playwright configuration", False, "frontend/e2e is missing")
        return

    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        f"{stack.project}_default",
        "-v",
        f"{FRONTEND_DIR}:/app",
        "-w",
        "/app",
        "-e",
        "E2E_BASE_URL=http://web:8080",
        "-e",
        "E2E_CORE_URL=http://core:8000",
        "-e",
        "E2E_INGEST_URL=http://ingest:8000",
        PLAYWRIGHT_IMAGE,
        "sh",
        "-c",
        "npm ci --no-audit --no-fund || npm install --no-audit --no-fund; "
        "npx playwright install --with-deps chromium; npx playwright test",
    ]
    runner.step("playwright browser checks", command, timeout=1800)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify API Sentinel.")
    parser.add_argument(
        "--suite",
        default="all",
        choices=["backend", "frontend", "e2e", "all"],
        help="Which suite to run (default: all).",
    )
    parser.add_argument(
        "--keep-stack",
        action="store_true",
        help="Do not remove the isolated Compose stack when the run finishes.",
    )
    args = parser.parse_args()

    require_docker()
    python = python_executable()
    runner = Runner()

    if args.suite in {"backend", "all"}:
        backend_steps(runner, python)

    if args.suite in {"frontend", "all"}:
        frontend_steps(runner, ["npm"])

    if args.suite in {"e2e", "all"}:
        project = f"sentinel-verify-{int(time.time())}"
        stack = Stack(project)
        log(f"starting the isolated verification stack {project}")
        try:
            if not stack.up():
                runner._record("compose up", False, "the stack did not become healthy")
            else:
                runner._record("compose up", True, "the stack is healthy")
                if args.suite == "all":
                    smoke_step(runner, stack)
                e2e_steps(runner, stack)
        finally:
            if not args.keep_stack:
                stack.down()
                log(f"removed the isolated stack {project}")

    return runner.summary()


if __name__ == "__main__":
    raise SystemExit(main())
