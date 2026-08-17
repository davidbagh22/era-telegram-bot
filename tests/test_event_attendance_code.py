import asyncio
from datetime import date, time

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.event_attendance import EventAttendanceSession
from app.database.models import Event, EventRegistration, PointTransaction, PortfolioItem, User
from app.services import event_attendance_service
from app.utils.constants import ApplicationStatus, EventStatus, RegistrationStatus, Role


async def _session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _seed_event(session):
    manager = User(
        telegram_id=990001,
        first_name="Администратор",
        role=Role.ADMIN,
        application_status=ApplicationStatus.APPROVED,
    )
    participant = User(
        telegram_id=990002,
        first_name="Участник",
        role=Role.PARTICIPANT,
        application_status=ApplicationStatus.APPROVED,
    )
    stranger = User(
        telegram_id=990003,
        first_name="Без регистрации",
        role=Role.PARTICIPANT,
        application_status=ApplicationStatus.APPROVED,
    )
    session.add_all([manager, participant, stranger])
    await session.flush()

    event = Event(
        title="Тестовое мероприятие",
        description="Проверка нового подтверждения посещения кодом.",
        event_date=date.today(),
        event_time=time(18, 0),
        location="Дом ЭРА",
        format="offline",
        responsible_id=manager.id,
        participant_limit=30,
        points_for_visit=25,
        selfie_required=True,
        status=EventStatus.REGISTRATION_CLOSED,
        created_by=manager.id,
    )
    session.add(event)
    await session.flush()
    registration = EventRegistration(
        event_id=event.id,
        user_id=participant.id,
        status=RegistrationStatus.REGISTERED,
    )
    session.add(registration)
    await session.commit()
    return manager, participant, stranger, event, registration


async def _attendance_code_opens_only_after_completion_and_awards_once() -> None:
    engine, factory = await _session_factory()
    try:
        async with factory() as session:
            manager, participant, _stranger, event, registration = await _seed_event(session)

            started = await event_attendance_service.start_event(
                session,
                event.id,
                actor_user_id=manager.id,
                bot=None,
                miniapp_url="",
            )
            assert started.event.status == EventStatus.ACTIVE
            assert started.session is not None
            assert started.session.attendance_code is not None
            assert len(started.session.attendance_code) == event_attendance_service.CODE_LENGTH

            before_finish = await event_attendance_service.participant_state(
                session, event.id, participant.id
            )
            assert before_finish.eligible is True
            assert before_finish.confirmation_open is False

            completed = await event_attendance_service.complete_event(
                session,
                event.id,
                actor_user_id=manager.id,
                bot=None,
                miniapp_url="",
            )
            assert completed.event.status == EventStatus.COMPLETED
            assert completed.confirmation_open is True

            after_finish = await event_attendance_service.participant_state(
                session, event.id, participant.id
            )
            assert after_finish.confirmation_open is True
            assert after_finish.confirmed is False

            with pytest.raises(ValueError, match="invalid_attendance_code"):
                await event_attendance_service.confirm_attendance(
                    session, event.id, participant.id, "WRONG123"
                )

            code = completed.session.attendance_code
            assert code is not None
            result = await event_attendance_service.confirm_attendance(
                session, event.id, participant.id, code
            )
            assert result.points_awarded == 25
            assert result.already_confirmed is False
            assert registration.status == RegistrationStatus.ATTENDED

            repeated = await event_attendance_service.confirm_attendance(
                session, event.id, participant.id, code
            )
            assert repeated.points_awarded == 0
            assert repeated.already_confirmed is True

            point_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(PointTransaction)
                    .where(
                        PointTransaction.user_id == participant.id,
                        PointTransaction.related_event_id == event.id,
                        PointTransaction.source_type == "event_attendance",
                    )
                )
                or 0
            )
            portfolio_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(PortfolioItem)
                    .where(
                        PortfolioItem.user_id == participant.id,
                        PortfolioItem.related_event_id == event.id,
                        PortfolioItem.item_type == "event",
                    )
                )
                or 0
            )
            assert point_count == 1
            assert portfolio_count == 1
    finally:
        await engine.dispose()


def test_attendance_code_opens_only_after_completion_and_awards_once() -> None:
    asyncio.run(_attendance_code_opens_only_after_completion_and_awards_once())


async def _attendance_code_rejects_unregistered_user() -> None:
    engine, factory = await _session_factory()
    try:
        async with factory() as session:
            manager, _participant, stranger, event, _registration = await _seed_event(session)
            started = await event_attendance_service.start_event(
                session,
                event.id,
                actor_user_id=manager.id,
                bot=None,
                miniapp_url="",
            )
            await event_attendance_service.complete_event(
                session,
                event.id,
                actor_user_id=manager.id,
                bot=None,
                miniapp_url="",
            )
            assert started.session is not None
            code = started.session.attendance_code
            assert code is not None
            with pytest.raises(ValueError, match="not_registered"):
                await event_attendance_service.confirm_attendance(
                    session, event.id, stranger.id, code
                )
    finally:
        await engine.dispose()


def test_attendance_code_rejects_unregistered_user() -> None:
    asyncio.run(_attendance_code_rejects_unregistered_user())


def test_generated_codes_are_human_friendly_and_do_not_use_ambiguous_symbols() -> None:
    codes = {event_attendance_service.generate_attendance_code() for _ in range(100)}
    assert len(codes) == 100
    assert all(len(code) == event_attendance_service.CODE_LENGTH for code in codes)
    assert all(set(code) <= set(event_attendance_service.CODE_ALPHABET) for code in codes)
    assert all(not set(code) & set("01IO") for code in codes)
