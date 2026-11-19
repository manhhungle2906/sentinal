#!/usr/bin/env python3
"""Seed the repeatable API Sentinel demo.

The script provisions a demo owner account, a workspace and an API source,
then submits the synthetic detection scenarios through the local ingestion
endpoint. Everything is submitted to the configured local stack only.

Usage:
    python3 scripts/demo.py [--scenario all]
    python3 scripts/demo.py --scenario failed_login_burst
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "demo"))

from _common import (
    HttpClient,
    log,
    require_python_312,
    wait_for_http,
    write_env_value,
)

# The demo scenarios use the Python 3.12 standard library, so the script
# restarts itself with a 3.12+ interpreter when the host default is older.
require_python_312()

from scenarios import SCENARIOS, build_scenario

DEMO_EMAIL = "demo-owner@example.com"
DEMO_PASSWORD = "demo-owner-password"
DEMO_WORKSPACE = "Sentinel Demo"
DEMO_SOURCE_LABEL = "Demo API"

EXPECTED_RULES = ("failed_login_burst", "high_request_volume", "repeated_access_denial")


def fail(message: str) -> None:
    log(f"ERROR: {message}")
    raise SystemExit(1)


def sign_in(client: HttpClient) -> None:
    """Register the demo owner, or sign in when the account already exists."""
    status, _ = client.post(
        "/api/auth/register",
        body={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD,
            "display_name": "Demo Owner",
        },
    )
    if status in (200, 201):
        log("registered the demo owner account")
        return
    status, body = client.post(
        "/api/auth/login", body={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
    )
    if status != 200:
        fail(f"could not sign in as the demo owner: {status} {body}")
    log("signed in as the existing demo owner account")


def ensure_workspace(client: HttpClient) -> str:
    """Return the demo workspace id, creating the workspace when needed."""
    status, workspaces = client.get("/api/workspaces")
    if status != 200 or not isinstance(workspaces, list):
        fail(f"could not list workspaces: {status} {workspaces}")
    for workspace in workspaces:
        if workspace.get("name") == DEMO_WORKSPACE:
            log(f"using the existing workspace {DEMO_WORKSPACE}")
            return str(workspace["id"])
    status, workspace = client.post(
        "/api/workspaces", body={"name": DEMO_WORKSPACE}, headers=client.csrf_header()
    )
    if status != 201 or not isinstance(workspace, dict):
        fail(f"could not create the workspace: {status} {workspace}")
    log(f"created the workspace {DEMO_WORKSPACE}")
    return str(workspace["id"])


def ensure_source(client: HttpClient, workspace_id: str) -> tuple[str, str]:
    """Return ``(source_id, ingestion_key)`` for the demo source.

    The raw key is only returned when the source is created, so an existing
    source has its key rotated to obtain a usable credential.
    """
    status, sources = client.get("/api/sources", headers={"X-Workspace-Id": workspace_id})
    if status != 200 or not isinstance(sources, list):
        fail(f"could not list sources: {status} {sources}")
    headers = {"X-Workspace-Id": workspace_id, **client.csrf_header()}
    for source in sources:
        if source.get("label") == DEMO_SOURCE_LABEL and source.get("is_active"):
            status, rotated = client.post(f"/api/sources/{source['id']}/rotate", headers=headers)
            if status != 200 or not isinstance(rotated, dict):
                fail(f"could not rotate the source key: {status} {rotated}")
            log(f"rotated the ingestion key of the existing source {DEMO_SOURCE_LABEL}")
            return str(source["id"]), str(rotated["ingestion_key"])
    status, created = client.post(
        "/api/sources", body={"label": DEMO_SOURCE_LABEL}, headers=headers
    )
    if status != 201 or not isinstance(created, dict):
        fail(f"could not create the source: {status} {created}")
    log(f"created the source {DEMO_SOURCE_LABEL}")
    return str(created["id"]), str(created["ingestion_key"])


def submit_event(ingest_url: str, key: str, payload: dict) -> int:
    """Submit one synthetic event record to the ingestion endpoint."""
    request = urllib.request.Request(
        ingest_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Source-Key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def restart_demo_service() -> bool:
    """Recreate the Demo API container so it picks up the ingestion key."""
    if shutil.which("docker") is None:
        return False
    repo_root = Path(__file__).resolve().parent.parent
    command = [
        "docker",
        "compose",
        "--profile",
        "demo",
        "up",
        "-d",
        "--force-recreate",
        "demo",
    ]
    log(f"$ {' '.join(command)}")
    try:
        result = subprocess.run(
            command,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as error:
        log(f"could not restart the demo service: {error}")
        return False
    if result.returncode != 0:
        log(f"could not restart the demo service:\n{result.stderr}")
        return False
    return True


def trigger_real_demo_request(demo_url: str) -> None:
    """Make a genuine request against the Demo API so real telemetry is produced."""
    for path in ("/products", "/products/p-1001"):
        try:
            with urllib.request.urlopen(f"{demo_url}{path}", timeout=15) as response:
                response.read()
        except urllib.error.HTTPError:
            # A 404 is still telemetry; the Demo API records every request.
            pass
        except Exception as error:
            fail(f"the demo API did not answer on {demo_url}{path}: {error}")
    log(f"sent ordinary requests to the demo API at {demo_url}")


def wait_for_alerts(client: HttpClient, workspace_id: str, timeout: float = 120.0) -> list[str]:
    """Poll the alert list until the three rule types are present."""
    deadline = time.monotonic() + timeout
    seen: set[str] = set()
    while time.monotonic() < deadline:
        status, page = client.get("/api/alerts", headers={"X-Workspace-Id": workspace_id})
        if status == 200 and isinstance(page, dict):
            for alert in page.get("items", []):
                seen.add(str(alert.get("rule_key")))
            if not [rule for rule in EXPECTED_RULES if rule not in seen]:
                return sorted(seen)
        time.sleep(2)
    return sorted(seen)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the API Sentinel demo data.")
    parser.add_argument(
        "--scenario",
        default="all",
        choices=["all", *sorted(SCENARIOS)],
        help="Which synthetic scenario to submit (default: all).",
    )
    parser.add_argument(
        "--core-url", default="http://localhost:8000", help="Direct Core API base URL."
    )
    parser.add_argument(
        "--ingest-url",
        default="http://localhost:8001/ingest/v1/events",
        help="Ingestion endpoint URL.",
    )
    parser.add_argument("--demo-url", default="http://localhost:9000", help="Demo API base URL.")
    parser.add_argument(
        "--skip-real-request",
        action="store_true",
        help="Do not send ordinary requests to the Demo API.",
    )
    parser.add_argument(
        "--no-restart-demo",
        action="store_true",
        help="Do not recreate the Demo API container after writing the ingestion key.",
    )
    args = parser.parse_args()

    client = HttpClient(args.core_url)
    sign_in(client)
    workspace_id = ensure_workspace(client)
    source_id, ingestion_key = ensure_source(client, workspace_id)
    log(f"demo source id {source_id}")

    # The Demo API container reads the key from the environment.
    write_env_value("DEMO_SOURCE_KEY", ingestion_key)
    log("stored the demo ingestion key in .env (DEMO_SOURCE_KEY)")
    if not args.no_restart_demo:
        if restart_demo_service():
            log("recreated the demo service so it uses the new ingestion key")
        else:
            log(
                "WARNING: the demo service could not be recreated; "
                "run `docker compose --profile demo up -d --force-recreate demo` manually"
            )

    if not args.skip_real_request:
        wait_for_http(f"{args.demo_url}/health/live", timeout=90)
        trigger_real_demo_request(args.demo_url)

    names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    submitted = 0
    for name in names:
        events = build_scenario(name)
        for event in events:
            status = submit_event(args.ingest_url, ingestion_key, event.to_payload())
            if status not in (200, 202):
                fail(f"the ingestion endpoint rejected a scenario event: {status}")
            submitted += 1
        log(f"submitted the scenario {name} ({len(events)} event records)")

    log(f"submitted {submitted} synthetic event records in total")

    seen = wait_for_alerts(client, workspace_id)
    missing = [rule for rule in EXPECTED_RULES if rule not in seen]
    if missing:
        log(f"ERROR: the following rule types did not raise an alert: {', '.join(missing)}")
        log(f"alerts seen: {', '.join(seen) if seen else 'none'}")
        return 1

    log(f"all three rule types raised an alert: {', '.join(EXPECTED_RULES)}")
    log("demo seeding complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
