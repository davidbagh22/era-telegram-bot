from __future__ import annotations

import asyncio
import os

from sqlalchemy import text

from app.config import Settings
from app.database.session import create_engine_and_sessionmaker
from app.services.seed_service import seed_reference_data

TIMESTAMP_TABLES = (
    "activity_metrics",
    "community_mission_templates",
    "task_squads",
    "task_subtasks",
    "media_content_items",
    "media_channel_deliveries",
    "media_content_tasks",
    "media_library_items",
    "media_requests",
    "media_chat_notices",
    "media_attachments",
)


async def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    settings = Settings(
        bot_token="0000000000:POSTGRESMIGRATIONSMOKE",
        database_url=database_url,
    )
    engine, session_factory = create_engine_and_sessionmaker(database_url)

    # This is the same startup seed path the Render web process executes after
    # `alembic upgrade heads`. It must succeed against a migrated PostgreSQL DB,
    # not only against Base.metadata.create_all() on SQLite.
    async with session_factory() as session:
        await seed_reference_data(session, settings)

    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                """
                SELECT table_name, column_name, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = ANY(:tables)
                  AND column_name IN ('created_at', 'updated_at')
                ORDER BY table_name, column_name
                """
            ),
            {"tables": list(TIMESTAMP_TABLES)},
        )
        rows = result.mappings().all()

        found = {(row["table_name"], row["column_name"]): row["column_default"] for row in rows}
        failures: list[str] = []
        for table_name in TIMESTAMP_TABLES:
            for column_name in ("created_at", "updated_at"):
                key = (table_name, column_name)
                if key not in found:
                    failures.append(f"missing {table_name}.{column_name}")
                elif not found[key]:
                    failures.append(f"missing DB default on {table_name}.{column_name}")
        if failures:
            raise RuntimeError("PostgreSQL timestamp schema drift: " + "; ".join(failures))

        mission_count = int(
            await connection.scalar(text("SELECT count(*) FROM community_mission_templates")) or 0
        )
        media_count = int(
            await connection.scalar(text("SELECT count(*) FROM media_content_items")) or 0
        )
        if mission_count <= 0:
            raise RuntimeError("startup seed created no community mission templates")
        if media_count <= 0:
            raise RuntimeError("startup seed created no media content items")

    await engine.dispose()
    print(
        f"PostgreSQL migration/startup smoke passed: "
        f"missions={mission_count}, media_items={media_count}"
    )


if __name__ == "__main__":
    asyncio.run(main())
