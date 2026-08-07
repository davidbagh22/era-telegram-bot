"""Seeds a throwaway database for E2E testing (see frontend/e2e/).

Creates the schema with `Base.metadata.create_all` — the same approach the
existing unit test suite already uses against SQLite (see
tests/test_activity_service.py etc.) — rather than running the real Alembic
migration chain, since several accumulated migrations are not wrapped in
`batch_alter_table()` and SQLite's limited `ALTER TABLE` support makes that
chain SQLite-incompatible. Migration correctness itself is verified
separately (single-head check, upgrade/downgrade smoke test — see
docs/ERA_PLATFORM_PROGRESS.md) against a real Postgres, not here.

Usage:
    DATABASE_URL=sqlite+aiosqlite:///./e2e.db python scripts/e2e_seed.py

Must be run once, before starting the server the E2E suite drives against,
and both must point at the same file path (not `:memory:`, which is
per-connection and wouldn't be shared with the server process).
"""

from __future__ import annotations

import asyncio
from datetime import date, time, timedelta

from app.config import get_settings
from app.database.base import Base
from app.database.models import Event, User
from app.database.session import create_engine_and_sessionmaker
from app.utils.constants import ApplicationStatus, EventStatus, Role

# Fixed, well-known IDs so frontend/e2e/*.spec.ts can reference them directly
# via ?devTelegramId=<id> without querying the DB first.
PARTICIPANT_TELEGRAM_ID = 900001
LEADER_TELEGRAM_ID = 900002
ADMIN_TELEGRAM_ID = 900003
PENDING_APPLICANT_TELEGRAM_ID = 900004
# Dedicated fixture for pending_sync.spec.ts, kept separate from
# PENDING_APPLICANT_TELEGRAM_ID above: admin.spec.ts approves that one
# through the Admin UI's single global "Одобрить" button, which would
# become ambiguous (Playwright strict-mode violation) if a second pending
# application were visible in the same queue at the same time. This one is
# approved by pending_sync.spec.ts directly through the API instead, so it
# never appears next to the other one in the Admin UI.
PENDING_SYNC_APPLICANT_TELEGRAM_ID = 900005


async def seed() -> None:
    settings = get_settings()
    engine, session_factory = create_engine_and_sessionmaker(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        admin = User(
            telegram_id=ADMIN_TELEGRAM_ID,
            first_name="E2E Admin",
            role=Role.ADMIN,
            application_status=ApplicationStatus.APPROVED,
        )
        session.add_all(
            [
                User(
                    telegram_id=PARTICIPANT_TELEGRAM_ID,
                    first_name="E2E Participant",
                    role=Role.PARTICIPANT,
                    application_status=ApplicationStatus.APPROVED,
                ),
                User(
                    telegram_id=LEADER_TELEGRAM_ID,
                    first_name="E2E Leader",
                    role=Role.LEADER,
                    application_status=ApplicationStatus.APPROVED,
                ),
                admin,
                User(
                    telegram_id=PENDING_APPLICANT_TELEGRAM_ID,
                    first_name="E2E Pending Applicant",
                    role=Role.PARTICIPANT,
                    application_status=ApplicationStatus.PENDING,
                    city="Ереван",
                    occupation="Тестировщик",
                    motivation="Хочу помогать проверять ЭРА",
                ),
                User(
                    telegram_id=PENDING_SYNC_APPLICANT_TELEGRAM_ID,
                    first_name="E2E Sync Applicant",
                    role=Role.PARTICIPANT,
                    application_status=ApplicationStatus.PENDING,
                    city="Ереван",
                    occupation="Тестировщик",
                    motivation="Проверяю автообновление Mini App",
                ),
            ]
        )
        await session.flush()  # assigns admin.id, used as the event's creator
        session.add(
            Event(
                title="E2E тестовое мероприятие",
                description="Создано seed-скриптом для E2E-проверки регистрации.",
                event_date=date.today() + timedelta(days=14),
                event_time=time(18, 0),
                location="Онлайн",
                format="online",
                status=EventStatus.REGISTRATION_OPEN,
                points_for_visit=5,
                created_by=admin.id,
            )
        )
        await session.commit()

    await engine.dispose()
    print(
        "E2E fixtures seeded: "
        f"participant={PARTICIPANT_TELEGRAM_ID}, leader={LEADER_TELEGRAM_ID}, "
        f"admin={ADMIN_TELEGRAM_ID}, pending_applicant={PENDING_APPLICANT_TELEGRAM_ID}, "
        f"pending_sync_applicant={PENDING_SYNC_APPLICANT_TELEGRAM_ID}"
    )


if __name__ == "__main__":
    asyncio.run(seed())
