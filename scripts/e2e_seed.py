"""Seeds a throwaway database for E2E testing (see frontend/e2e/)."""
from __future__ import annotations

import asyncio
from datetime import date, time, timedelta

from sqlalchemy import select

from app.config import get_settings
from app.database.base import Base
from app.database.event_experience import EventExperience, EventReminderDelivery  # noqa: F401
from app.database.models import Badge, Event, EventActivity, EventActivitySubmission, PointTransaction, User, UserBadge
from app.database.session import create_engine_and_sessionmaker
from app.services.participation_lifecycle_service import complete_onboarding
from app.utils.constants import ApplicationStatus, EventStatus, Role

PARTICIPANT_TELEGRAM_ID = 900001
LEADER_TELEGRAM_ID = 900002
ADMIN_TELEGRAM_ID = 900003
PENDING_APPLICANT_TELEGRAM_ID = 900004
PENDING_SYNC_APPLICANT_TELEGRAM_ID = 900005
AUCTION_BIDDER_TELEGRAM_ID = 900006
REWARD_REDEEMER_TELEGRAM_ID = 900007
ACTIVITY_SUBMITTER_TELEGRAM_ID = 900008

async def seed() -> None:
    settings = get_settings()
    engine, session_factory = create_engine_and_sessionmaker(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        admin = User(telegram_id=ADMIN_TELEGRAM_ID, first_name="E2E Admin", role=Role.ADMIN, application_status=ApplicationStatus.APPROVED)
        leader = User(telegram_id=LEADER_TELEGRAM_ID, first_name="E2E Leader", role=Role.LEADER, application_status=ApplicationStatus.APPROVED)
        participant = User(telegram_id=PARTICIPANT_TELEGRAM_ID, first_name="E2E Participant", role=Role.PARTICIPANT, application_status=ApplicationStatus.APPROVED)
        pending = User(telegram_id=PENDING_APPLICANT_TELEGRAM_ID, first_name="E2E Pending Applicant", role=Role.PARTICIPANT, application_status=ApplicationStatus.PENDING, city="Ереван", occupation="Тестировщик", motivation="Хочу помогать проверять ЭРА")
        pending_sync = User(telegram_id=PENDING_SYNC_APPLICANT_TELEGRAM_ID, first_name="E2E Sync Applicant", role=Role.PARTICIPANT, application_status=ApplicationStatus.PENDING, city="Ереван", occupation="Тестировщик", motivation="Проверяю автообновление Mini App")
        bidder = User(telegram_id=AUCTION_BIDDER_TELEGRAM_ID, first_name="E2E Auction Bidder", role=Role.PARTICIPANT, application_status=ApplicationStatus.APPROVED)
        redeemer = User(telegram_id=REWARD_REDEEMER_TELEGRAM_ID, first_name="E2E Reward Redeemer", role=Role.PARTICIPANT, application_status=ApplicationStatus.APPROVED)
        activity_submitter = User(telegram_id=ACTIVITY_SUBMITTER_TELEGRAM_ID, first_name="E2E Activity Submitter", role=Role.PARTICIPANT, application_status=ApplicationStatus.APPROVED)
        session.add_all([participant, leader, admin, pending, pending_sync, bidder, redeemer, activity_submitter])
        await session.flush()

        e2e_telegram_ids = (PARTICIPANT_TELEGRAM_ID, LEADER_TELEGRAM_ID, ADMIN_TELEGRAM_ID, PENDING_APPLICANT_TELEGRAM_ID, PENDING_SYNC_APPLICANT_TELEGRAM_ID, AUCTION_BIDDER_TELEGRAM_ID, REWARD_REDEEMER_TELEGRAM_ID, ACTIVITY_SUBMITTER_TELEGRAM_ID)
        e2e_users = (await session.scalars(select(User).where(User.telegram_id.in_(e2e_telegram_ids)))).all()
        for seeded_user in e2e_users:
            await complete_onboarding(session, seeded_user)

        session.add(PointTransaction(user_id=bidder.id, points=1000, reason="E2E seed balance", source_type="e2e_seed", idempotency_key=f"e2e_seed:auction_bidder:{bidder.id}"))
        session.add(PointTransaction(user_id=redeemer.id, points=1000, reason="E2E seed balance", source_type="e2e_seed", idempotency_key=f"e2e_seed:reward_redeemer:{redeemer.id}"))
        badge = Badge(name="E2E Тестовый значок", description="Выдан seed-скриптом для проверки портфолио.")
        session.add(badge)
        await session.flush()
        session.add(UserBadge(user_id=participant.id, badge_id=badge.id, reason="Автоматическая проверка портфолио", awarded_by=admin.id))
        session.add(Event(title="E2E тестовое мероприятие", description="Создано seed-скриптом для E2E-проверки регистрации.", event_date=date.today() + timedelta(days=14), event_time=time(18, 0), location="Онлайн", format="online", status=EventStatus.REGISTRATION_OPEN, points_for_visit=5, created_by=admin.id))
        completed_event = Event(title="E2E завершённое мероприятие", description="Создано seed-скриптом для E2E-проверки активностей.", event_date=date.today() - timedelta(days=1), event_time=time(18, 0), location="Онлайн", format="online", status=EventStatus.COMPLETED, points_for_visit=5, created_by=admin.id, responsible_id=leader.id)
        session.add(completed_event)
        await session.flush()
        activity = EventActivity(event_id=completed_event.id, title="E2E активность", description="Проверка полного цикла: лидер -> админ.", submission_type="text", points=15, requires_review=True, is_active=True)
        session.add(activity)
        await session.flush()
        session.add(EventActivitySubmission(activity_id=activity.id, user_id=activity_submitter.id, text="Готовый результат для E2E-проверки.", status="pending"))
        await session.commit()
    await engine.dispose()
    print("E2E fixtures seeded: participant=900001, leader=900002, admin=900003, pending_applicant=900004, pending_sync_applicant=900005, auction_bidder=900006, reward_redeemer=900007, activity_submitter=900008")

if __name__ == "__main__":
    asyncio.run(seed())
