from __future__ import annotations

import asyncio
import os
import subprocess

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine


LOCK_KEY = 938_271_604


def code_heads() -> set[str]:
    config = Config("alembic.ini")
    return set(ScriptDirectory.from_config(config).get_heads())


async def database_heads(connection: AsyncConnection) -> set[str]:
    table_exists = await connection.scalar(text("SELECT to_regclass('public.alembic_version')"))
    if table_exists is None:
        return set()
    result = await connection.execute(text("SELECT version_num FROM alembic_version"))
    return set(result.scalars().all())


async def migrate() -> None:
    expected_heads = code_heads()
    database_url = os.environ["DATABASE_URL"]
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            if await database_heads(connection) == expected_heads:
                return

            await connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": LOCK_KEY})
            try:
                # Another instance may have completed the migration while this
                # instance was waiting for the lock. Re-check before invoking
                # Alembic so ordinary restarts do not rerun the migration path.
                if await database_heads(connection) != expected_heads:
                    subprocess.run(["alembic", "upgrade", "heads"], check=True)
            finally:
                await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "app.webapp:app",
            "--host",
            "0.0.0.0",
            "--port",
            os.environ.get("PORT", "8000"),
        ],
    )
