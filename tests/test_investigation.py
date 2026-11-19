"""Integration tests for the alert investigation workflow.

The tests cover the collaboration path required by the release: two members
investigate the same alert, assignment is restricted to owners and analysts,
comments and history persist, and a non-member cannot reach the data.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sentinel.common.db import get_db
from sentinel.core.app import create_app

PASSWORD = "correct-horse-battery"


@pytest.fixture
def clean_session(clean_db):
    """Return the shared test session used by every client in this module."""
    return clean_db


@pytest.fixture
def client(clean_session) -> Iterator[TestClient]:
    with _client_for(clean_session) as test_client:
        yield test_client


@pytest.fixture
def client_factory(clean_session):
    def _factory() -> TestClient:
        return _client_for(clean_session)

    return _factory


@contextmanager
def _client_for(session) -> Iterator[TestClient]:
    app = create_app()

    def _override_get_db():
        yield session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client


def _register(client: TestClient, email: str, display_name: str = "Member") -> None:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": display_name},
    )
    assert response.status_code == 201, response.text


def _csrf(client: TestClient) -> str:
    return client.cookies.get("sentinel_csrf")


def _workspace(client: TestClient, name: str = "Acme Security") -> dict:
    response = client.post(
        "/api/workspaces", json={"name": name}, headers={"X-CSRF-Token": _csrf(client)}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _source(client: TestClient, workspace_id: str) -> dict:
    response = client.post(
        "/api/sources",
        json={"label": "Demo API"},
        headers={"X-Workspace-Id": workspace_id, "X-CSRF-Token": _csrf(client)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _insert_alert(db, workspace_id: uuid.UUID, source_id: uuid.UUID) -> str:
    """Insert an alert (and its trigger event) directly and return the alert id."""
    from datetime import UTC, datetime

    from sentinel.common.models import Alert, SecurityEvent

    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    event = SecurityEvent(
        source_id=source_id,
        event_uuid=uuid.uuid4(),
        received_at=base,
        request_at=base,
        source_ip="203.0.113.11",
        route_template="POST /auth/login",
        method="POST",
        status_code=401,
        duration_ms=10,
        event_type="login_failed",
    )
    db.add(event)
    db.flush()

    alert = Alert(
        workspace_id=workspace_id,
        source_id=source_id,
        rule_key="failed_login_burst",
        severity="high",
        status="new",
        source_ip="203.0.113.11",
        count_at_trigger=5,
        threshold=5,
        window_seconds=120,
        interval_start=base - timedelta(seconds=120),
        interval_end=base,
        trigger_event_id=event.id,
        suppressed_until=base + timedelta(seconds=120),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return str(alert.id)


def test_two_members_investigate_the_same_alert(
    client: TestClient, client_factory, clean_db
) -> None:
    _register(client, "owner@example.com", "Owner")
    workspace = _workspace(client)

    with client_factory() as analyst:
        _register(analyst, "analyst@example.com", "Analyst")
        added = client.post(
            f"/api/workspaces/{workspace['id']}/members",
            json={"email": "analyst@example.com", "role": "analyst"},
            headers={"X-CSRF-Token": _csrf(client)},
        )
        assert added.status_code == 201, added.text

        source = _source(client, workspace["id"])
        alert_id = _insert_alert(clean_db, uuid.UUID(workspace["id"]), uuid.UUID(source["id"]))

        # The analyst can read the alert and its evidence.
        detail = analyst.get(f"/api/alerts/{alert_id}", headers={"X-Workspace-Id": workspace["id"]})
        assert detail.status_code == 200, detail.text
        assert detail.json()["rule_key"] == "failed_login_burst"
        assert detail.json()["status"] == "new"

        # The analyst posts a comment; the author is recorded.
        comment = analyst.post(
            f"/api/alerts/{alert_id}/comments",
            json={"body": "Checked the upstream logs, no breach."},
            headers={"X-Workspace-Id": workspace["id"], "X-CSRF-Token": _csrf(analyst)},
        )
        assert comment.status_code == 201, comment.text
        assert comment.json()["author_name"] == "Analyst"

        # The owner assigns the alert to the analyst.
        assigned = client.patch(
            f"/api/alerts/{alert_id}/assignee",
            json={"assignee_id": analyst.get("/api/auth/me").json()["id"]},
            headers={"X-Workspace-Id": workspace["id"], "X-CSRF-Token": _csrf(client)},
        )
        assert assigned.status_code == 200, assigned.text
        assert assigned.json()["assignee_name"] == "Analyst"

        # The owner moves the alert to investigating and then resolves it.
        investigating = client.patch(
            f"/api/alerts/{alert_id}/status",
            json={"status": "investigating"},
            headers={"X-Workspace-Id": workspace["id"], "X-CSRF-Token": _csrf(client)},
        )
        assert investigating.status_code == 200, investigating.text
        assert investigating.json()["status"] == "investigating"

        resolved = client.patch(
            f"/api/alerts/{alert_id}/status",
            json={"status": "resolved"},
            headers={"X-Workspace-Id": workspace["id"], "X-CSRF-Token": _csrf(client)},
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "resolved"
        assert resolved.json()["resolved_at"] is not None

        # A terminal alert no longer accepts status changes.
        again = client.patch(
            f"/api/alerts/{alert_id}/status",
            json={"status": "investigating"},
            headers={"X-Workspace-Id": workspace["id"], "X-CSRF-Token": _csrf(client)},
        )
        assert again.status_code == 409

        # The history records every change with the actor.
        history = analyst.get(
            f"/api/alerts/{alert_id}/history", headers={"X-Workspace-Id": workspace["id"]}
        )
        assert history.status_code == 200
        actions = [entry["action"] for entry in history.json()]
        assert "commented" in actions
        assert "assignee_changed" in actions
        assert actions.count("status_changed") == 2


def test_a_viewer_cannot_comment_or_change_the_status(
    client: TestClient, client_factory, clean_db
) -> None:
    _register(client, "owner@example.com", "Owner")
    workspace = _workspace(client)

    with client_factory() as viewer:
        _register(viewer, "viewer@example.com", "Viewer")
        client.post(
            f"/api/workspaces/{workspace['id']}/members",
            json={"email": "viewer@example.com", "role": "viewer"},
            headers={"X-CSRF-Token": _csrf(client)},
        )
        source = _source(client, workspace["id"])
        alert_id = _insert_alert(clean_db, uuid.UUID(workspace["id"]), uuid.UUID(source["id"]))

        # A viewer may read the alert.
        assert (
            viewer.get(
                f"/api/alerts/{alert_id}", headers={"X-Workspace-Id": workspace["id"]}
            ).status_code
            == 200
        )

        # A viewer may not comment.
        comment = viewer.post(
            f"/api/alerts/{alert_id}/comments",
            json={"body": "Not allowed"},
            headers={"X-Workspace-Id": workspace["id"], "X-CSRF-Token": _csrf(viewer)},
        )
        assert comment.status_code == 403

        # A viewer may not change the status.
        status = viewer.patch(
            f"/api/alerts/{alert_id}/status",
            json={"status": "resolved"},
            headers={"X-Workspace-Id": workspace["id"], "X-CSRF-Token": _csrf(viewer)},
        )
        assert status.status_code == 403


def test_an_alert_cannot_be_assigned_to_a_viewer(
    client: TestClient, client_factory, clean_db
) -> None:
    _register(client, "owner@example.com", "Owner")
    workspace = _workspace(client)

    with client_factory() as viewer:
        _register(viewer, "viewer@example.com", "Viewer")
        client.post(
            f"/api/workspaces/{workspace['id']}/members",
            json={"email": "viewer@example.com", "role": "viewer"},
            headers={"X-CSRF-Token": _csrf(client)},
        )
        source = _source(client, workspace["id"])
        alert_id = _insert_alert(clean_db, uuid.UUID(workspace["id"]), uuid.UUID(source["id"]))

        viewer_id = viewer.get("/api/auth/me").json()["id"]
        response = client.patch(
            f"/api/alerts/{alert_id}/assignee",
            json={"assignee_id": viewer_id},
            headers={"X-Workspace-Id": workspace["id"], "X-CSRF-Token": _csrf(client)},
        )
        assert response.status_code == 400


def test_a_non_member_cannot_read_an_alert(client: TestClient, client_factory, clean_db) -> None:
    _register(client, "owner@example.com", "Owner")
    workspace = _workspace(client)
    source = _source(client, workspace["id"])
    alert_id = _insert_alert(clean_db, uuid.UUID(workspace["id"]), uuid.UUID(source["id"]))

    with client_factory() as outsider:
        _register(outsider, "stranger@example.com", "Stranger")
        response = outsider.get(
            f"/api/alerts/{alert_id}", headers={"X-Workspace-Id": workspace["id"]}
        )
        assert response.status_code == 404

        events = outsider.get("/api/events", headers={"X-Workspace-Id": workspace["id"]})
        assert events.status_code == 404

        stats = outsider.get("/api/dashboard/stats", headers={"X-Workspace-Id": workspace["id"]})
        assert stats.status_code == 404


def test_alert_status_transitions_follow_the_allowed_flow(client: TestClient, clean_db) -> None:
    _register(client, "owner@example.com", "Owner")
    workspace = _workspace(client)
    source = _source(client, workspace["id"])
    alert_id = _insert_alert(clean_db, uuid.UUID(workspace["id"]), uuid.UUID(source["id"]))

    # New -> False positive is allowed directly.
    response = client.patch(
        f"/api/alerts/{alert_id}/status",
        json={"status": "false_positive"},
        headers={"X-Workspace-Id": workspace["id"], "X-CSRF-Token": _csrf(client)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "false_positive"
