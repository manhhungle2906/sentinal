"""Alembic environment for API Sentinel."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sentinel.common.config import get_settings
from sentinel.common.db import ipv4_connect_args
from sentinel.common.models import Base
from sqlalchemy import create_engine, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Some managed PostgreSQL providers publish an IPv6 address for the
    # hostname. A runtime without IPv6 connectivity would then fail with
    # "Network is unreachable", so the IPv4 address is pinned here.
    connect_args = ipv4_connect_args(settings.database_url)
    engine_kwargs: dict[str, object] = {
        "poolclass": pool.NullPool,
        "future": True,
    }
    if connect_args:
        engine_kwargs["connect_args"] = connect_args
    connectable = create_engine(settings.database_url, **engine_kwargs)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
