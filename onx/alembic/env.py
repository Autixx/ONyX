from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from onx.core.config import get_settings
from onx.db.base import Base


ROOT_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = ROOT_DIR / "alembic.ini"

config = context.config
if config.config_file_name is None:
    config.set_main_option("config_file_name", str(ALEMBIC_INI_PATH))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

import onx.db.models  # noqa: F401

target_metadata = Base.metadata


def _ensure_alembic_version_column_capacity(connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    row = connection.execute(
        text(
            """
            SELECT character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'alembic_version'
              AND column_name = 'version_num'
            """
        )
    ).first()
    if row is None:
        # Table does not exist yet. Pre-create it with a wide column so that
        # Alembic skips its own CREATE (which defaults to VARCHAR(32)).
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(128) NOT NULL)"
        ))
        return
    current_length = row[0]
    if current_length is None or current_length >= 128:
        return
    connection.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"))


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
        _ensure_alembic_version_column_capacity(connection)
        if connection.in_transaction():
            connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
