#!/usr/bin/env python3
"""Seed the live deployment with a realistic scenario for the walkthrough.

The script registers an account, creates a workspace and three API sources,
then submits synthetic events that cross each of the three detection rules.
It prints the credentials and the identifiers the walkthrough needs.

Usage:
    python3 scripts/seed_live.py --base-url https://sentinel-web-ryxl.onrender.com
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from typing import Any

# The deterministic base time keeps the scenario isolated from the wall
# clock. The three scenarios use separate sources and IPs so every alert
# is unambiguous.
BASE_TIME = "2026-01-01T00:00:00Z"


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
    parser = argparse.ArgumentParser(description="Seed the live deployment.")
    parser.add_argument("--base-url", default="https://sentinel-web-ryxl.onrender.com")
    parser.add_argument("--email", default="demo@apisentinel.dev")
    parser.add_argument("--password", default="Sentinel-demo-password-2026!")
    args = parser.parse_args(argv[1:])

    base = args.base_url.rstrip("/")
    client = Client(base)
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        log(f"{'PASS' if ok else 'FAIL'}  {name}" + (f": {detail}" if detail else ""))
        if not ok:
            failures.append(name)

    status, body = client.post(
        "/api/auth/register",
        body={
            "email": args.email,
            "password": args.password,
            "display_name": "Demo Owner",
        },
    )
    if status == 409:
        log(f"note: {args.email} already exists, signing in")
        status, body = client.post(
            "/api/auth/login", body={"email": args.email, "password": args.password}
        )
    check("register or login", status in {200, 201}, f"status {status}")

    status, body = client.get("/api/workspaces")
    workspaces = body if isinstance(body, list) else []
    workspace_id = workspaces[0].get("id") if workspaces else None
    if not workspace_id:
        status, body = client.post_csrf("/api/workspaces", body={"name": "Demo Workspace"})
        workspace_id = body.get("id") if isinstance(body, dict) else None
    check("workspace", bool(workspace_id), str(workspace_id))
    if not workspace_id:
        return 1

    ws_header = {"X-Workspace-Id": workspace_id}

    # --- sources --------------------------------------------------------
    sources: dict[str, dict[str, str]] = {}
    for label in ("Demo API", "Login Gateway", "Partner API"):
        status, body = client.get("/api/sources", headers=ws_header)
        existing = body if isinstance(body, list) else []
        found = next((s for s in existing if s.get("label") == label), None)
        if found:
            status, body = client.post_csrf(f"/api/sources/{found['id']}/rotate", headers=ws_header)
        else:
            status, body = client.post_csrf(
                "/api/sources", body={"label": label}, headers=ws_header
            )
        if status in {200, 201} and isinstance(body, dict):
            sources[label] = {
                "id": body["id"],
                "key": body["ingestion_key"],
            }
        check(f"source '{label}'", label in sources, f"status {status}")

    if len(sources) != 3:
        log("")
        log(f"{len(failures)} check(s) failed")
        return 1

    # --- ordinary traffic on the Demo API -------------------------------
    normal = [
        ("request", "198.51.100.10", "/api/products", "GET", 200),
        ("request", "198.51.100.10", "/api/products/{id}", "GET", 200),
        ("request", "198.51.100.11", "/api/cart", "POST", 201),
        ("request", "198.51.100.11", "/api/checkout", "POST", 200),
        ("request", "198.51.100.12", "/api/products", "GET", 200),
    ]
    demo = sources["Demo API"]
    for index, (kind, ip, route, method, status_code) in enumerate(normal):
        client.post(
            "/ingest/v1/events",
            body={
                "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"demo-normal-{index}")),
                "event_type": kind,
                "occurred_at": BASE_TIME,
                "source_ip": ip,
                "route_template": route,
                "method": method,
                "status_code": status_code,
                "duration_ms": 20 + index,
            },
            headers={"X-Source-Key": demo["key"]},
        )
    check("ordinary traffic submitted", True)

    # --- scenario 1: failed_login_burst (5 in 2 minutes) ---------------
    login = sources["Login Gateway"]
    for index in range(6):
        client.post(
            "/ingest/v1/events",
            body={
                "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"demo-login-{index}")),
                "event_type": "login_failed",
                "occurred_at": BASE_TIME,
                "source_ip": "198.51.100.50",
                "route_template": "/api/auth/login",
                "method": "POST",
                "status_code": 401,
                "duration_ms": 30 + index,
            },
            headers={"X-Source-Key": login["key"]},
        )
    check("failed_login_burst scenario submitted", True)

    # --- scenario 2: high_request_volume (101 in 1 minute) --------------
    #
    # The rule counts the *server receipt timestamps*, so the events have to
    # land inside a single 60 second window. Submitting them one after the
    # other spreads the receipts over roughly two minutes and the crossing
    # never happens. The bounded thread pool below keeps them inside the
    # window without turning this into a request flood against a real API.
    partner = sources["Partner API"]

    def submit_volume(index: int) -> int:
        sender = Client(base)
        status, _ = sender.post(
            "/ingest/v1/events",
            body={
                "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"demo-volume-{index}")),
                "event_type": "request",
                "occurred_at": BASE_TIME,
                "source_ip": "198.51.100.77",
                "route_template": "/api/search",
                "method": "GET",
                "status_code": 200,
                "duration_ms": 5,
            },
            headers={"X-Source-Key": partner["key"]},
        )
        return status

    with ThreadPoolExecutor(max_workers=16) as pool:
        volume_statuses = list(pool.map(submit_volume, range(104)))
    accepted = sum(1 for status in volume_statuses if status in {200, 202})
    check(
        "high_request_volume scenario submitted",
        accepted == len(volume_statuses),
        f"{accepted}/{len(volume_statuses)} accepted",
    )

    # --- scenario 3: repeated_access_denial (10 in 5 minutes) -----------
    denial = sources["Partner API"]
    for index in range(12):
        client.post(
            "/ingest/v1/events",
            body={
                "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"demo-denial-{index}")),
                "event_type": "request",
                "occurred_at": BASE_TIME,
                "source_ip": "198.51.100.88",
                "route_template": "/api/admin/reports",
                "method": "GET",
                "status_code": 403,
                "duration_ms": 8,
            },
            headers={"X-Source-Key": denial["key"]},
        )
    check("repeated_access_denial scenario submitted", True)

    # --- wait for the detector ------------------------------------------
    found: dict[str, bool] = {}
    for _ in range(40):
        status, body = client.get("/api/alerts?limit=100", headers=ws_header)
        items = body.get("items", []) if isinstance(body, dict) else (body or [])
        for alert in items:
            key = alert.get("rule_key")
            if key:
                found[key] = True
        if len(found) >= 3:
            break
        time.sleep(2)

    for rule in ("failed_login_burst", "high_request_volume", "repeated_access_denial"):
        check(f"alert {rule}", bool(found.get(rule)))

    log("")
    log("=== walkthrough data ===")
    log(f"base_url   : {base}")
    log(f"email      : {args.email}")
    log(f"password   : {args.password}")
    log(f"workspace  : {workspace_id}")
    for label, data in sources.items():
        log(f"source     : {label} = {data['id']}")
    log("")

    if failures:
        log(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    log("seed complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
