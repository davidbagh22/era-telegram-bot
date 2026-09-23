from logging.config import fileConfig

import sqlalchemy as sa
from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.database import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _bootstrap_fresh_database(connection) -> bool:
    """Create and stamp a genuinely empty database at the current schema.

    The historical initial migration intentionally used live ORM metadata, so
    replaying every old migration on a brand-new database would try to add
    columns that create_all() has already created. Existing databases must
    still follow the normal Alembic chain; only a database with zero tables is
    eligible for this bootstrap path.
    """
    if sa.inspect(connection).get_table_names():
        return False

    target_metadata.create_all(bind=connection)
    version_table = sa.Table(
        "alembic_version",
        sa.MetaData(),
        sa.Column("version_num", sa.String(length=32), nullable=False, primary_key=True),
    )
    version_table.create(bind=connection, checkfirst=True)
    heads = list(context.script.get_heads())
    if heads:
        connection.execute(
            version_table.insert(),
            [{"version_num": revision} for revision in heads],
        )
    return True


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, compare_type=True
    )
    with context.begin_transaction():
        if _bootstrap_fresh_database(connection):
            return
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_async_migrations())
