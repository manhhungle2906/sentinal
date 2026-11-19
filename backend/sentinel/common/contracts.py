"""Shared contracts (Pydantic DTOs) used by Core, Ingest and the frontend."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress, field_validator

from sentinel.common.constants import ALLOWED_EVENT_TYPES, ALLOWED_METHODS

RouteTemplate = Annotated[str, Field(min_length=1, max_length=255)]
Method = Annotated[str, Field(min_length=1, max_length=10)]
StatusCode = Annotated[int, Field(ge=100, le=599)]
SourceIp = IPvAnyAddress
EventUuid = uuid.UUID


class IngestEventRequest(BaseModel):
    """Payload accepted by the ingestion API.

    Only whitelisted metadata is accepted. Bodies, headers and tokens are
    never part of this contract.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event_id: EventUuid
    event_type: Literal["request", "login_failed"] = "request"
    occurred_at: datetime | None = None
    source_ip: SourceIp
    route_template: RouteTemplate
    method: Method
    status_code: StatusCode
    duration_ms: Annotated[int, Field(ge=0, le=3_600_000)] | None = None

    @field_validator("event_type")
    @classmethod
    def _known_event_type(cls, value: str) -> str:
        if value not in ALLOWED_EVENT_TYPES:
            raise ValueError("event_type must be one of request, login_failed")
        return value

    @field_validator("method")
    @classmethod
    def _known_method(cls, value: str) -> str:
        upper = value.upper()
        if upper not in ALLOWED_METHODS:
            raise ValueError("method is not allowed")
        return upper

    @field_validator("route_template")
    @classmethod
    def _clean_route(cls, value: str) -> str:
        if "?" in value or "#" in value:
            raise ValueError("route_template must not contain a query string or fragment")
        return value

    @field_validator("occurred_at")
    @classmethod
    def _aware_occurred_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value


class IngestEventResponse(BaseModel):
    event_id: uuid.UUID
    status: Literal["accepted", "duplicate"]
    received_at: datetime


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    checked_at: datetime


class ReadyResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    checked_at: datetime
    database: Literal["ok", "unavailable"]
