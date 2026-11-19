#!/usr/bin/env python3
"""Smoke check for a running API Sentinel stack.

The script verifies that the developer-facing proxy answers on the default
browser URL, that the Core and Ingest health paths respond, and that the
detector heartbeat in PostgreSQL is fresh.

Usage:
    python3 scripts/smoke.py [--base-url http://localhost:8080]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import HttpClient, log


def check(name: str, ok: bool, detail: str) -> bool:
    status = "PASS" if ok else "FAIL"
    log(f"{status}  {name}: {detail}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke check the running stack.")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8080",
        help="Developer-facing proxy base URL (default: http://localhost:8080).",
    )
    parser.add_argument(
        "--core-url",
        default="http://localhost:8000",
        help="Direct Core API base URL (default: http://localhost:8000).",
    )
    parser.add_argument(
        "--ingest-url",
        default="http://localhost:8001",
        help="Direct Ingest API base URL (default: http://localhost:8001).",
    )
    args = parser.parse_args()

    failures = 0
    client = HttpClient(args.base_url)

    # 1. The browser URL serves the SPA.
    try:
        with urllib.request.urlopen(args.base_url, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace")
            ok = response.status == 200 and '<div id="root"' in body
            failures += 0 if check("browser url", ok, f"status {response.status}") else 1
    except urllib.error.HTTPError as error:
        failures += 0 if check("browser url", False, f"status {error.code}") else 1
    except Exception as error:
        failures += 0 if check("browser url", False, str(error)) else 1

    # 2. The same-origin Core health routes respond through the proxy.
    for route in ("/health/live", "/health/ready"):
        status, body = client.get(route)
        ok = status == 200 and isinstance(body, dict) and body.get("status") in {"ok", "degraded"}
        failures += 0 if check(f"proxy {route}", ok, f"status {status} body {body}") else 1

    # 3. Core and Ingest answer directly as well.
    for label, base, routes in (
        ("core", args.core_url, ("/health/live", "/health/ready")),
        ("ingest", args.ingest_url, ("/health/live", "/health/ready")),
    ):
        direct = HttpClient(base)
        for route in routes:
            status, body = direct.get(route)
            ok = status == 200 and isinstance(body, dict)
            failures += 0 if check(f"{label} {route}", ok, f"status {status}") else 1

    # 4. The detector heartbeat is fresh (observed by Core).
    status, body = client.get("/health/detector")
    fresh = status == 200 and isinstance(body, dict) and body.get("status") == "ok"
    failures += 0 if check("detector heartbeat", fresh, json.dumps(body)) else 1

    if failures:
        log(f"smoke check failed: {failures} check(s) did not pass")
        return 1
    log("smoke check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
