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
from app.database.models import (
    Badge,
    Event,
    EventActivity,
    EventActivitySubmission,
    PointTransaction,
    User,
    UserBadge,
)
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
# Dedicated fixture for auctions.spec.ts: a real bid needs a real points
# balance, and PARTICIPANT_TELEGRAM_ID's balance must stay exactly 0 going
# into admin_people.spec.ts (which asserts an exact post-award total). A
# separate user avoids the two tests fighting over one balance.
AUCTION_BIDDER_TELEGRAM_ID = 900006
# Dedicated fixture for rewards.spec.ts: redeeming and exchanging a
# catalog reward really does debit points (unlike placing an auction bid),
# so this gets its own balance rather than reusing AUCTION_BIDDER_TELEGRAM_ID
# or PARTICIPANT_TELEGRAM_ID.
REWARD_REDEEMER_TELEGRAM_ID = 900007
# Dedicated fixture for event_activities.spec.ts: a real admin approval
# awards points, same reasoning as REWARD_REDEEMER_TELEGRAM_ID above — this
# submitter's balance must stay untouched by every other spec.
ACTIVITY_SUBMITTER_TELEGRAM_ID = 900008


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
        leader = User(
            telegram_id=LEADER_TELEGRAM_ID,
            first_name="E2E Leader",
            role=Role.LEADER,
            application_status=ApplicationStatus.APPROVED,
        )
        participant = User(
            telegram_id=PARTICIPANT_TELEGRAM_ID,
            first_name="E2E Participant",
            role=Role.PARTICIPANT,
            application_status=ApplicationStatus.APPROVED,
        )
        session.add_all(
            [
                participant,
                leader,
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
        bidder = User(
            telegram_id=AUCTION_BIDDER_TELEGRAM_ID,
            first_name="E2E Auction Bidder",
            role=Role.PARTICIPANT,
            application_status=ApplicationStatus.APPROVED,
        )
        redeemer = User(
            telegram_id=REWARD_REDEEMER_TELEGRAM_ID,
            first_name="E2E Reward Redeemer",
            role=Role.PARTICIPANT,
            application_status=ApplicationStatus.APPROVED,
        )
        activity_submitter = User(
            telegram_id=ACTIVITY_SUBMITTER_TELEGRAM_ID,
            first_name="E2E Activity Submitter",
            role=Role.PARTICIPANT,
            application_status=ApplicationStatus.APPROVED,
        )
        session.add_all([bidder, redeemer, activity_submitter])
        await session.flush()  # assigns participant.id/admin.id/leader.id/bidder.id/redeemer.id/activity_submitter.id, used below
        session.add(
            PointTransaction(
                user_id=bidder.id,
                points=1000,
                reason="E2E seed balance",
                source_type="e2e_seed",
                idempotency_key=f"e2e_seed:auction_bidder:{bidder.id}",
            )
        )
        session.add(
            PointTransaction(
                user_id=redeemer.id,
                points=1000,
                reason="E2E seed balance",
                source_type="e2e_seed",
                idempotency_key=f"e2e_seed:reward_redeemer:{redeemer.id}",
            )
        )
        # A real Badge/UserBadge award — not a bot-only-FSM thing, this is
        # DB state any admin award creates — so responsive.spec.ts and any
        # future portfolio-view spec have a real, stable "Достижения" entry
        # to assert on. See docs/FINAL_PRODUCTION_ACCEPTANCE.md #266 for
        # why upload/delete still isn't covered here: those genuinely do
        # need a live Telegram client (file upload FSM), portfolio *view*
        # doesn't.
        badge = Badge(name="E2E Тестовый значок", description="Выдан seed-скриптом для проверки портфолио.")
        session.add(badge)
        await session.flush()  # assigns badge.id
        session.add(
            UserBadge(
                user_id=participant.id,
                badge_id=badge.id,
                reason="Автоматическая проверка портфолио",
                awarded_by=admin.id,
            )
        )
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
        # Completed event, run by the E2E leader, so event_activities.spec.ts
        # can exercise the full leader -> admin review pipeline. A real
        # bot-side proof submission needs a live Telegram client (out of
        # reach for Playwright), so the "pending" submission below stands in
        # for one — same gap the Task-submission deep link has, with no
        # existing E2E coverage of that FSM either.
        completed_event = Event(
            title="E2E завершённое мероприятие",
            description="Создано seed-скриптом для E2E-проверки активностей.",
            event_date=date.today() - timedelta(days=1),
            event_time=time(18, 0),
            location="Онлайн",
            format="online",
            status=EventStatus.COMPLETED,
            points_for_visit=5,
            created_by=admin.id,
            responsible_id=leader.id,
        )
        session.add(completed_event)
        await session.flush()
        activity = EventActivity(
            event_id=completed_event.id,
            title="E2E активность",
            description="Проверка полного цикла: лидер -> админ.",
            submission_type="text",
            points=15,
            requires_review=True,
            is_active=True,
        )
        session.add(activity)
        await session.flush()
        session.add(
            EventActivitySubmission(
                activity_id=activity.id,
                user_id=activity_submitter.id,
                text="Готовый результат для E2E-проверки.",
                status="pending",
            )
        )
        await session.commit()

    await engine.dispose()
    print(
        "E2E fixtures seeded: "
        f"participant={PARTICIPANT_TELEGRAM_ID}, leader={LEADER_TELEGRAM_ID}, "
        f"admin={ADMIN_TELEGRAM_ID}, pending_applicant={PENDING_APPLICANT_TELEGRAM_ID}, "
        f"pending_sync_applicant={PENDING_SYNC_APPLICANT_TELEGRAM_ID}, "
        f"auction_bidder={AUCTION_BIDDER_TELEGRAM_ID}, "
        f"reward_redeemer={REWARD_REDEEMER_TELEGRAM_ID}, "
        f"activity_submitter={ACTIVITY_SUBMITTER_TELEGRAM_ID}"
    )


if __name__ == "__main__":
    asyncio.run(seed())
