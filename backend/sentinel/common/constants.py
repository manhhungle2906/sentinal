"""Domain constants shared across services."""

from __future__ import annotations

from enum import StrEnum


class WorkspaceRole(StrEnum):
    OWNER = "owner"
    ANALYST = "analyst"
    VIEWER = "viewer"


class AlertStatus(StrEnum):
    NEW = "new"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class AlertSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EventType(StrEnum):
    REQUEST = "request"
    LOGIN_FAILED = "login_failed"


ALLOWED_EVENT_TYPES = {EventType.REQUEST.value, EventType.LOGIN_FAILED.value}

ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

# Roles allowed to change an alert (assign, comment, status).
INVESTIGATOR_ROLES = {WorkspaceRole.OWNER.value, WorkspaceRole.ANALYST.value}

# Roles allowed to manage members and sources.
ADMIN_ROLES = {WorkspaceRole.OWNER.value}

# Allowed status transitions in the MVP. Terminal states are read-only.
ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    AlertStatus.NEW.value: {
        AlertStatus.INVESTIGATING.value,
        AlertStatus.RESOLVED.value,
        AlertStatus.FALSE_POSITIVE.value,
    },
    AlertStatus.INVESTIGATING.value: {AlertStatus.RESOLVED.value, AlertStatus.FALSE_POSITIVE.value},
    AlertStatus.RESOLVED.value: set(),
    AlertStatus.FALSE_POSITIVE.value: set(),
}

TERMINAL_ALERT_STATUSES = {AlertStatus.RESOLVED.value, AlertStatus.FALSE_POSITIVE.value}
