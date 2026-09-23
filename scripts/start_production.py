from __future__ import annotations

import asyncio
import os
import subprocess

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


LOCK_KEY = 938_271_604


async def migrate() -> None:
    database_url = os.environ["DATABASE_URL"]
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": LOCK_KEY})
            try:
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
