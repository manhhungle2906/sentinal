#!/usr/bin/env python3
"""Check that a PostgreSQL connection string really works.

The script prints the parsed target, the resolved addresses and the server
answer. It never prints the password.

Usage:
    python3 scripts/check_db.py "postgresql+psycopg://user:password@host/db?sslmode=require"
"""

from __future__ import annotations

import socket
import sys
from urllib.parse import urlsplit


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <connection-string>", file=sys.stderr)
        return 2

    raw = argv[1]
    parts = urlsplit(raw.replace("postgresql+psycopg", "postgresql"))
    host = parts.hostname
    port = parts.port or 5432

    print(f"scheme   : {raw.split('://', 1)[0]}")
    print(f"host     : {host}")
    print(f"port     : {port}")
    print(f"database : {parts.path.lstrip('/')}")
    print(f"user     : {parts.username}")
    print(f"password : {'set' if parts.password else 'MISSING'}")

    if not host:
        print("ERROR: the connection string has no host")
        return 1

    try:
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    except OSError as error:
        print(f"ERROR: the host does not resolve: {error}")
        return 1

    print("addresses:")
    for family, _type, _proto, _canon, sockaddr in infos:
        label = "IPv6" if family == socket.AF_INET6 else "IPv4"
        print(f"  {label} {sockaddr[0]}")

    try:
        import psycopg
    except ImportError:
        print("ERROR: psycopg is not installed; run this from the backend virtual environment")
        return 1

    try:
        with (
            psycopg.connect(
                raw.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=20
            ) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("select version()")
            row = cursor.fetchone()
        print("RESULT  : connected")
        print(f"server  : {str(row[0]).split(',')[0]}")
        return 0
    except Exception as error:
        # The script reports every failure, so a broad catch is intentional.
        print(f"RESULT  : FAILED - {type(error).__name__}")
        print(f"detail  : {str(error)[:600]}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
