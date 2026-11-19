"""Integration tests for the Core API: auth, workspaces, sources, monitoring."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sentinel.common.db import get_db
from sentinel.core.app import create_app


@pytest.fixture
def client(clean_db) -> TestClient:
    """A Core API client bound to the isolated test database."""
    with _client_for(clean_db) as test_client:
        yield test_client


@pytest.fixture
def client_factory(clean_db):
    """Factory for additional clients sharing the same test database."""

    def _factory() -> TestClient:
        return _client_for(clean_db)

    return _factory


@contextmanager
def _client_for(session) -> Iterator[TestClient]:
    app = create_app()

    def _override_get_db():
        yield session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client


def _register(
    client: TestClient, email: str = "owner@example.com", password: str = "correct-horse-battery"
):
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": "Owner"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _csrf(client: TestClient) -> str:
    return client.cookies.get("sentinel_csrf")


def _workspace(client: TestClient, name: str = "Acme Security") -> dict:
    response = client.post(
        "/api/workspaces",
        json={"name": name},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def test_register_returns_the_user_and_sets_session_cookies(client: TestClient) -> None:
    payload = _register(client)
    assert payload["user"]["email"] == "owner@example.com"
    assert "sentinel_session" in client.cookies
    assert "sentinel_csrf" in client.cookies


def test_register_rejects_a_duplicate_email(client: TestClient) -> None:
    _register(client)
    response = client.post(
        "/api/auth/register",
        json={
            "email": "owner@example.com",
            "password": "correct-horse-battery",
            "display_name": "Again",
        },
    )
    assert response.status_code == 409


def test_login_succeeds_and_logout_revokes_the_session(client: TestClient) -> None:
    _register(client)
    response = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    )
    assert response.status_code == 200

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "owner@example.com"

    logout = client.post("/api/auth/logout", headers={"X-CSRF-Token": _csrf(client)})
    assert logout.status_code == 204

    after = client.get("/api/auth/me")
    assert after.status_code == 401


def test_login_with_a_wrong_password_is_rejected(client: TestClient) -> None:
    _register(client)
    response = client.post(
        "/api/auth/login", json={"email": "owner@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_me_without_a_session_returns_401(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_state_change_without_a_csrf_token_is_rejected(client: TestClient) -> None:
    _register(client)
    client.cookies.delete("sentinel_csrf")
    response = client.post("/api/workspaces", json={"name": "No CSRF"})
    assert response.status_code == 403


def test_state_change_from_another_origin_is_rejected(client: TestClient) -> None:
    _register(client)
    response = client.post(
        "/api/workspaces",
        json={"name": "Cross origin"},
        headers={
            "X-CSRF-Token": _csrf(client),
            "Origin": "http://evil.example.com",
        },
    )
    assert response.status_code == 403
    assert "cross-origin" in response.json()["detail"]


def test_state_change_from_the_same_origin_with_a_different_port_is_rejected(
    client: TestClient,
) -> None:
    _register(client)
    response = client.post(
        "/api/workspaces",
        json={"name": "Other port"},
        headers={
            "X-CSRF-Token": _csrf(client),
            "Origin": "http://testserver:9999",
            "Host": "testserver:8080",
        },
    )
    assert response.status_code == 403


def test_state_change_is_accepted_when_the_proxy_forwards_the_host_without_a_port(
    client: TestClient,
) -> None:
    """A reverse proxy that drops the port must not break the same-origin check.

    The browser sends ``Origin: http://web:8080`` while a proxy that forwards
    ``Host: web`` reaches the API. The host still matches, so the request is
    allowed; a different host is still rejected.
    """
    _register(client)
    response = client.post(
        "/api/workspaces",
        json={"name": "Proxied"},
        headers={"X-CSRF-Token": _csrf(client), "Origin": "http://web:8080", "Host": "web"},
    )
    assert response.status_code == 201, response.text


# ---------------------------------------------------------------------------
# Workspaces and roles
# ---------------------------------------------------------------------------
def test_workspace_list_and_membership(client: TestClient) -> None:
    _register(client)
    workspace = _workspace(client)

    listed = client.get("/api/workspaces")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [workspace["id"]]
    assert listed.json()[0]["role"] == "owner"

    members = client.get(f"/api/workspaces/{workspace['id']}/members")
    assert members.status_code == 200
    assert members.json()[0]["role"] == "owner"


def test_a_user_outside_the_workspace_gets_404(client: TestClient, client_factory) -> None:
    _register(client, "owner@example.com")
    workspace = _workspace(client)

    # A second browser session belonging to a non-member.
    with client_factory() as other:
        other.post(
            "/api/auth/register",
            json={
                "email": "stranger@example.com",
                "password": "correct-horse-battery",
                "display_name": "Stranger",
            },
        )
        response = other.get(f"/api/workspaces/{workspace['id']}/members")
        assert response.status_code == 404


def test_owner_can_add_an_existing_account_as_analyst(client: TestClient, client_factory) -> None:
    _register(client, "owner@example.com")
    workspace = _workspace(client)

    with client_factory() as analyst:
        analyst.post(
            "/api/auth/register",
            json={
                "email": "analyst@example.com",
                "password": "correct-horse-battery",
                "display_name": "Analyst",
            },
        )

        response = client.post(
            f"/api/workspaces/{workspace['id']}/members",
            json={"email": "analyst@example.com", "role": "analyst"},
            headers={"X-CSRF-Token": _csrf(client)},
        )
        assert response.status_code == 201, response.text
        assert response.json()["role"] == "analyst"


def test_owner_cannot_add_an_unknown_account(client: TestClient) -> None:
    _register(client)
    workspace = _workspace(client)
    response = client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"email": "nobody@example.com", "role": "viewer"},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
def test_source_creation_shows_the_raw_key_once(client: TestClient) -> None:
    _register(client)
    workspace = _workspace(client)

    response = client.post(
        "/api/sources",
        json={"label": "Demo API"},
        headers={"X-Workspace-Id": workspace["id"], "X-CSRF-Token": _csrf(client)},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["ingestion_key"].startswith("sn_")
    assert body["is_active"] is True

    listed = client.get("/api/sources", headers={"X-Workspace-Id": workspace["id"]})
    assert listed.status_code == 200
    # The raw key is never returned again.
    assert "ingestion_key" not in listed.json()[0]


def test_viewer_cannot_create_a_source(client: TestClient, client_factory) -> None:
    _register(client, "owner@example.com")
    workspace = _workspace(client)

    with client_factory() as viewer:
        viewer.post(
            "/api/auth/register",
            json={
                "email": "viewer@example.com",
                "password": "correct-horse-battery",
                "display_name": "Viewer",
            },
        )
        client.post(
            f"/api/workspaces/{workspace['id']}/members",
            json={"email": "viewer@example.com", "role": "viewer"},
            headers={"X-CSRF-Token": _csrf(client)},
        )
        response = viewer.post(
            "/api/sources",
            json={"label": "Not allowed"},
            headers={"X-Workspace-Id": workspace["id"], "X-CSRF-Token": _csrf(viewer)},
        )
        assert response.status_code == 403


def test_rotating_a_key_invalidates_the_previous_one(client: TestClient) -> None:
    _register(client)
    workspace = _workspace(client)
    created = client.post(
        "/api/sources",
        json={"label": "Demo API"},
        headers={"X-Workspace-Id": workspace["id"], "X-CSRF-Token": _csrf(client)},
    ).json()

    rotated = client.post(
        f"/api/sources/{created['id']}/rotate",
        headers={"X-Workspace-Id": workspace["id"], "X-CSRF-Token": _csrf(client)},
    )
    assert rotated.status_code == 200
    assert rotated.json()["ingestion_key"] != created["ingestion_key"]


def test_revoking_a_source_marks_it_inactive(client: TestClient) -> None:
    _register(client)
    workspace = _workspace(client)
    created = client.post(
        "/api/sources",
        json={"label": "Demo API"},
        headers={"X-Workspace-Id": workspace["id"], "X-CSRF-Token": _csrf(client)},
    ).json()

    revoked = client.post(
        f"/api/sources/{created['id']}/revoke",
        headers={"X-Workspace-Id": workspace["id"], "X-CSRF-Token": _csrf(client)},
    )
    assert revoked.status_code == 200
    assert revoked.json()["is_active"] is False


# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------
def test_events_and_dashboard_require_a_workspace_header(client: TestClient) -> None:
    _register(client)
    assert client.get("/api/events").status_code == 400
    assert client.get("/api/dashboard/stats").status_code == 400


def test_dashboard_returns_zero_filled_buckets(client: TestClient) -> None:
    _register(client)
    workspace = _workspace(client)
    response = client.get(
        "/api/dashboard/stats",
        headers={"X-Workspace-Id": workspace["id"]},
        params={"start": "2026-01-01T00:00:00Z", "end": "2026-01-01T00:10:00Z"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_requests"] == 0
    assert body["bucket_seconds"] == 60
    assert len(body["traffic"]) == 11


def test_alerts_list_is_empty_for_a_fresh_workspace(client: TestClient) -> None:
    _register(client)
    workspace = _workspace(client)
    response = client.get("/api/alerts", headers={"X-Workspace-Id": workspace["id"]})
    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


def test_health_endpoints_are_available(client: TestClient) -> None:
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"

    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"
