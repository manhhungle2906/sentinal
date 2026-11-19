"""Database engine, session factory and FastAPI dependency.

The engine is created from ``SENTINEL_DATABASE_URL``. Some managed
PostgreSQL providers (Neon, for example) publish both IPv4 and IPv6
addresses for the same hostname. A runtime without IPv6 connectivity
therefore resolves the hostname to an IPv6 address and fails with
``Network is unreachable`` even though the database is reachable over
IPv4.

To keep the deployment portable, the hostname is resolved once at start-up
and the IPv4 address is passed to libpq as ``hostaddr``. The hostname is
still sent as ``host``, so TLS SNI and the certificate verification keep
working against the pooled endpoint.
"""

from __future__ import annotations

import socket
from collections.abc import Generator
from urllib.parse import urlsplit

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from sentinel.common.config import get_settings

_settings = get_settings()


def _resolve_ipv4(host: str, port: int) -> str | None:
    """Return the first IPv4 address of ``host``, or ``None``."""
    try:
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    except OSError:
        return None
    for family, _type, _proto, _canon, sockaddr in infos:
        if family == socket.AF_INET:
            return str(sockaddr[0])
    return None


def ipv4_connect_args(database_url: str) -> dict[str, str]:
    """Return the libpq arguments that force an IPv4 connection.

    The result is empty when the URL has no host, when the host already
    resolves to IPv4 only, or when the lookup fails. The connection then
    behaves exactly as before.
    """
    try:
        url: URL = make_url(database_url)
    except Exception:
        # A malformed URL must not break start-up.
        return {}

    host = url.host
    if not host:
        return {}

    # An explicit hostaddr in the URL wins: the operator already made a
    # deliberate choice.
    if "hostaddr" in (url.query or {}):
        return {}

    try:
        port = url.port or 5432
    except ValueError:
        port = 5432

    address = _resolve_ipv4(host, port)
    if address is None:
        return {}
    return {"hostaddr": address}


def build_engine(database_url: str, **kwargs: object):
    """Create a SQLAlchemy engine with the IPv4-safe connection arguments."""
    connect_args = ipv4_connect_args(database_url)
    if connect_args:
        supplied = kwargs.pop("connect_args", None) or {}
        connect_args.update(supplied)  # type: ignore[arg-type]
        kwargs["connect_args"] = connect_args
    return create_engine(database_url, **kwargs)


engine = build_engine(
    _settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def describe_database_target() -> str:
    """Return a sanitized description of the database target for the logs."""
    try:
        parts = urlsplit(_settings.database_url.replace("postgresql+psycopg", "postgresql"))
    except ValueError:
        return "unknown"
    return f"{parts.hostname}:{parts.port or 5432}"
