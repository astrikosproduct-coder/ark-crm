"""
Alembic environment for ARK CRM.

The database URL is NOT written into alembic.ini. It is read from the same
place the application reads it — app.database, which loads backend/.env — so
there is exactly one connection string in the project and a migration can
never run against a different database than the API.

`target_metadata` is app.database.Base.metadata with every model imported, so
`alembic revision --autogenerate` sees the whole schema.
"""

from logging.config import fileConfig

from alembic import context

# Importing app.models registers every table on Base.metadata. The import of
# `models` looks unused — it is not; it is what populates the metadata below.
from app import models  # noqa: F401
from app.database import DATABASE_URL, Base, engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout rather than running it — `alembic upgrade --sql`."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the live database."""
    with engine.connect() as connection:
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
