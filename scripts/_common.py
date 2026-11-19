"""Shared helpers for the API Sentinel orchestration scripts.

The scripts are deliberately dependency-free: they only use the Python
standard library so they run on macOS, Linux and Windows without a virtual
environment. On Windows use ``py -3.12`` if ``python3`` is not available.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
DEMO_DIR = REPO_ROOT / "demo"


def log(message: str) -> None:
    """Print a progress line immediately (stdout may be piped)."""
    print(message, flush=True)


def fail(message: str) -> None:
    """Print an error and exit with a non-zero status."""
    print(f"ERROR: {message}", file=sys.stderr, flush=True)
    raise SystemExit(1)


# --------------------------------------------------------------------------
# Interpreter discovery
# --------------------------------------------------------------------------


def python_executable() -> list[str]:
    """Return the command that runs a Python 3.12+ interpreter.

    The project virtual environment wins, then a versioned interpreter on
    PATH, then the Windows ``py`` launcher.
    """
    candidates: list[list[str]] = []
    venv_python = (
        BACKEND_DIR / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    if venv_python.exists():
        candidates.append([str(venv_python)])
    for name in ("python3.12", "python3", "python"):
        found = shutil.which(name)
        if found:
            candidates.append([found])
    py_launcher = shutil.which("py")
    if py_launcher:
        candidates.append([py_launcher, "-3.12"])

    for command in candidates:
        try:
            result = subprocess.run(
                [*command, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode != 0:
            continue
        try:
            major, minor = (int(part) for part in result.stdout.strip().split(".")[:2])
        except ValueError:
            continue
        if (major, minor) >= (3, 12):
            return command
    fail(
        "a Python 3.12+ interpreter is required. Install one (for example "
        "`uv python install 3.12`) or create backend/.venv."
    )
    raise AssertionError("unreachable")


def require_python_312() -> None:
    """Re-exec the script with a Python 3.12+ interpreter when needed.

    The project requires Python 3.12. On macOS the system interpreter is
    often older, so the script restarts itself with a suitable one.
    """
    if sys.version_info >= (3, 12):
        return
    command = python_executable()
    log(f"restarting with {' '.join(command)} (Python 3.12+ required)")
    os.execv(command[0], [*command, str(Path(__file__).resolve()), *sys.argv[1:]])


# --------------------------------------------------------------------------
# Command execution
# --------------------------------------------------------------------------


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command, echoing it first, and return the completed process."""
    printable = " ".join(command)
    log(f"$ {printable}")
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=merged_env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        fail(f"command not found: {command[0]}")
    except subprocess.TimeoutExpired:
        fail(f"command timed out after {timeout}s: {printable}")
    if check and result.returncode != 0:
        sys.stdout.write(result.stdout or "")
        sys.stderr.write(result.stderr or "")
        fail(f"command failed with exit code {result.returncode}: {printable}")
    return result


def docker_compose(
    *args: str, project: str | None = None, env: dict[str, str] | None = None
) -> list[str]:
    """Build the ``docker compose`` command line."""
    command = ["docker", "compose"]
    if project:
        command += ["-p", project]
    command += list(args)
    return command


def require_docker() -> None:
    """Fail early when the Docker daemon is not reachable."""
    if shutil.which("docker") is None:
        fail("docker is not installed or not on PATH")
    result = run(["docker", "info", "--format", "{{.ServerVersion}}"], check=False)
    if result.returncode != 0:
        fail("the Docker daemon is not running")
    log(f"Docker server version {result.stdout.strip()}")


# --------------------------------------------------------------------------
# HTTP helpers
# --------------------------------------------------------------------------


class HttpClient:
    """A small cookie-aware JSON HTTP client."""

    def __init__(self, base_url: str = "", timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies),
            urllib.request.HTTPRedirectHandler(),
        )

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}{path}"

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        """Perform a request and return ``(status_code, parsed_body)``."""
        data = None
        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self._url(path), data=data, headers=request_headers, method=method
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                payload = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            payload = error.read()
            status = error.code
        if not payload:
            return status, None
        try:
            return status, json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return status, payload.decode("utf-8", errors="replace")

    def get(self, path: str, **kwargs: Any) -> tuple[int, Any]:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> tuple[int, Any]:
        return self.request("POST", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> tuple[int, Any]:
        return self.request("PATCH", path, **kwargs)

    def cookie(self, name: str) -> str | None:
        for cookie in self.cookies:
            if cookie.name == name:
                return cookie.value
        return None

    def csrf_header(self) -> dict[str, str]:
        """Return the CSRF header pair for a state-changing request."""
        token = self.cookie("sentinel_csrf")
        return {"X-CSRF-Token": token} if token else {}


def wait_for_http(
    url: str,
    *,
    timeout: float = 120.0,
    interval: float = 2.0,
    expect_status: int = 200,
) -> bool:
    """Poll a URL until it answers with the expected status."""
    import time

    deadline = time.monotonic() + timeout
    last_error = "no attempt"
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status == expect_status:
                    return True
                last_error = f"status {response.status}"
        except urllib.error.HTTPError as error:
            last_error = f"status {error.code}"
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
        time.sleep(interval)
    log(f"timed out waiting for {url} ({last_error})")
    return False


def free_port() -> int:
    """Return a free TCP port on the loopback interface."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_env_value(key: str, value: str, env_path: Path | None = None) -> None:
    """Persist a value in the local .env file without duplicating the key."""
    path = env_path or (REPO_ROOT / ".env")
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[index] = f"{key}={value}"
            replaced = True
    if not replaced:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
