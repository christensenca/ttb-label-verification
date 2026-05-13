"""Alembic environment.

Wires `target_metadata` to `app.db.models.Base.metadata` and overrides the
`sqlalchemy.url` from `app.config.get_settings().database_url` so migrations
always honor the same env var the runtime engine reads.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject DB URL from app settings unless an explicit override has already been
# passed in via `config.set_main_option("sqlalchemy.url", …)` (e.g. by a test
# harness pointing at the test DB). The default `alembic init` ini ships
# `driver://user:pass@localhost/dbname` as a placeholder — treat that as unset.
_url_in_ini = config.get_main_option("sqlalchemy.url") or ""
if not _url_in_ini or _url_in_ini.startswith("driver://"):
    _settings_url = get_settings().database_url
    if _settings_url.startswith("postgres://"):
        _settings_url = "postgresql+psycopg://" + _settings_url[len("postgres://") :]
    elif _settings_url.startswith("postgresql://"):
        _settings_url = "postgresql+psycopg://" + _settings_url[len("postgresql://") :]
    config.set_main_option("sqlalchemy.url", _settings_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
