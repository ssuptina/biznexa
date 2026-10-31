from alembic import context
from biznexa import models  # noqa: F401
from biznexa.config import get_settings
from biznexa.db import Base
from sqlalchemy import engine_from_config, pool

config = context.config


def _alembic_database_url() -> str:
    """Escape percent signs for Alembic's ConfigParser-backed URL setting."""
    return get_settings().sqlalchemy_database_url.replace("%", "%%")


config.set_main_option("sqlalchemy.url", _alembic_database_url())
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().sqlalchemy_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
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
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
