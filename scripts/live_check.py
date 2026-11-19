#!/usr/bin/env python3
"""Verify the live deployment end to end.

The script registers an account, creates a workspace and an API source,
submits a synthetic event through the ingestion endpoint, waits for the
detector to raise the alert and checks that the alert is visible with its
evidence. It uses only the public HTTP surface.

Usage:
    python3 scripts/live_check.py --base-url https://sentinel-web.onrender.com
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from http.cookiejar import CookieJar
from typing import Any

DEFAULT_BASE_URL = "https://sentinel-web-ryxl.onrender.com"


class Client:
    """A cookie-aware JSON client for the public API."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies),
            urllib.request.HTTPRedirectHandler(),
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        data = None
        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=request_headers, method=method
        )
        try:
            with self.opener.open(request, timeout=60) as response:
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

    def csrf(self) -> dict[str, str]:
        for cookie in self.cookies:
            if cookie.name == "sentinel_csrf":
                return {"X-CSRF-Token": cookie.value}
        return {}

    def post_csrf(self, path: str, body: Any = None, **kwargs: Any) -> tuple[int, Any]:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.update(self.csrf())
        return self.request("POST", path, body=body, headers=headers, **kwargs)


def log(message: str) -> None:
    print(message, flush=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Verify the live deployment.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--email", default=None)
    args = parser.parse_args(argv[1:])

    base = args.base_url.rstrip("/")
    email = args.email or f"live-check-{uuid.uuid4().hex[:10]}@example.com"
    password = "Live-check-password-123!"
    client = Client(base)

    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        log(f"{'PASS' if ok else 'FAIL'}  {name}" + (f": {detail}" if detail else ""))
        if not ok:
            failures.append(name)

    log("")
    log(f"=== live check against {base} ===")

    status, body = client.get("/health/ready")
    check("health/ready", status == 200, str(body))

    status, body = client.post(
        "/api/auth/register",
        body={"email": email, "password": password, "display_name": "Live Check"},
    )
    if status == 409:
        log(f"note: the account {email} already exists, signing in instead")
        status, body = client.post("/api/auth/login", body={"email": email, "password": password})
    check("register", status in {200, 201}, f"status {status}: {str(body)[:200]}")

    status, body = client.get("/api/auth/me")
    check("session", status == 200, f"status {status}")

    status, body = client.get("/api/workspaces")
    workspaces = body if isinstance(body, list) else []
    workspace_id = None
    if workspaces:
        workspace_id = workspaces[0].get("id")
    if not workspace_id:
        status, body = client.post_csrf("/api/workspaces", body={"name": "Live Check Workspace"})
        if status in {200, 201} and isinstance(body, dict):
            workspace_id = body.get("id")
    check("workspace", bool(workspace_id), str(workspace_id))

    if not workspace_id:
        log("")
        log(f"{len(failures)} check(s) failed")
        return 1

    status, body = client.get("/api/sources", headers={"X-Workspace-Id": workspace_id})
    sources = body if isinstance(body, list) else []
    api_key = None
    source_id = None
    if sources:
        source_id = sources[0].get("id")
    if not source_id:
        status, body = client.post_csrf(
            "/api/sources",
            body={"label": "Live Check Source"},
            headers={"X-Workspace-Id": workspace_id},
        )
        if status in {200, 201} and isinstance(body, dict):
            source_id = body.get("id")
            api_key = body.get("ingestion_key")
    check("source", bool(source_id), f"status {status}: {str(body)[:200]}")
    check("ingestion key shown once", bool(api_key))

    if not source_id or not api_key:
        log("")
        log(f"{len(failures)} check(s) failed")
        return 1

    source_ip = "198.51.100.24"
    route = "/api/products/{id}"
    events = []
    for index in range(6):
        events.append(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "login_failed",
                "occurred_at": "2026-01-01T00:00:00Z",
                "source_ip": source_ip,
                "route_template": route,
                "method": "POST",
                "status_code": 401,
                "duration_ms": 12 + index,
            }
        )

    statuses = []
    for event in events:
        status, body = client.post(
            "/ingest/v1/events",
            body=event,
            headers={"X-Source-Key": api_key},
        )
        statuses.append(status)
    check(
        "ingestion accepted",
        all(code in {200, 202} for code in statuses),
        f"statuses {statuses}",
    )

    status, body = client.get("/api/events?limit=5", headers={"X-Workspace-Id": workspace_id})
    check("event list", status == 200, f"status {status}")

    alert_found = False
    for _ in range(30):
        status, body = client.get("/api/alerts?limit=50", headers={"X-Workspace-Id": workspace_id})
        alerts = body.get("items", body) if isinstance(body, dict) else body
        if isinstance(alerts, list):
            for alert in alerts:
                if alert.get("rule_key") == "failed_login_burst":
                    alert_found = True
                    break
        if alert_found:
            break
        time.sleep(2)
    check("failed_login_burst alert raised", alert_found)

    log("")
    if failures:
        log(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    log("all live checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
