"""Tests for the database connection helpers.

The IPv4 pinning exists because some managed PostgreSQL providers publish an
IPv6 address for the hostname. A runtime without IPv6 connectivity then
fails with ``Network is unreachable`` even though the database is reachable
over IPv4.
"""

from __future__ import annotations

from unittest.mock import patch

from sentinel.common.db import _resolve_ipv4, build_engine, ipv4_connect_args


def test_ipv4_connect_args_returns_empty_when_the_host_has_no_ipv4_address() -> None:
    with patch("sentinel.common.db._resolve_ipv4", return_value=None):
        assert ipv4_connect_args("postgresql+psycopg://u:p@example.com:5432/db") == {}


def test_ipv4_connect_args_pins_the_resolved_ipv4_address() -> None:
    with patch("sentinel.common.db._resolve_ipv4", return_value="203.0.113.10"):
        args = ipv4_connect_args("postgresql+psycopg://u:p@example.com:5432/db")

    assert args == {"hostaddr": "203.0.113.10"}


def test_ipv4_connect_args_keeps_an_explicit_hostaddr() -> None:
    url = "postgresql+psycopg://u:p@example.com:5432/db?hostaddr=198.51.100.7"

    with patch("sentinel.common.db._resolve_ipv4", return_value="203.0.113.10"):
        assert ipv4_connect_args(url) == {}


def test_ipv4_connect_args_ignores_a_malformed_url() -> None:
    assert ipv4_connect_args("not a url at all") == {}


def test_ipv4_connect_args_ignores_a_url_without_a_host() -> None:
    assert ipv4_connect_args("postgresql+psycopg:///sentinel") == {}


def test_resolve_ipv4_returns_an_ipv4_address() -> None:
    address = _resolve_ipv4("localhost", 5432)

    assert address is not None
    assert "." in address
    assert ":" not in address


def test_build_engine_passes_the_hostaddr_to_the_dialect() -> None:
    with (
        patch("sentinel.common.db._resolve_ipv4", return_value="203.0.113.10"),
        patch("sentinel.common.db.create_engine") as create_engine,
    ):
        build_engine("postgresql+psycopg://u:p@example.com:5432/db")

    assert create_engine.call_args.kwargs["connect_args"] == {"hostaddr": "203.0.113.10"}


def test_build_engine_without_an_ipv4_address_keeps_the_default_arguments() -> None:
    with (
        patch("sentinel.common.db._resolve_ipv4", return_value=None),
        patch("sentinel.common.db.create_engine") as create_engine,
    ):
        build_engine("postgresql+psycopg://u:p@example.com:5432/db")

    assert "connect_args" not in create_engine.call_args.kwargs


def test_build_engine_merges_the_supplied_connect_args() -> None:
    with (
        patch("sentinel.common.db._resolve_ipv4", return_value="203.0.113.10"),
        patch("sentinel.common.db.create_engine") as create_engine,
    ):
        build_engine(
            "postgresql+psycopg://u:p@example.com:5432/db",
            connect_args={"application_name": "sentinel"},
        )

    assert create_engine.call_args.kwargs["connect_args"] == {
        "hostaddr": "203.0.113.10",
        "application_name": "sentinel",
    }
