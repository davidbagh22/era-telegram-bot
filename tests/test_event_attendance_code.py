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


async def _confirmation_window_closes_without_losing_history() -> None:
    engine, factory = await _session_factory()
    try:
        async with factory() as session:
            manager, participant, _stranger, event, registration = await _seed_event(session)
            await event_attendance_service.start_event(
                session, event.id, actor_user_id=manager.id, bot=None, miniapp_url=""
            )
            completed = await event_attendance_service.complete_event(
                session, event.id, actor_user_id=manager.id, bot=None, miniapp_url=""
            )
            assert completed.session and completed.session.attendance_code

            closed = await event_attendance_service.close_confirmation(
                session, event.id, actor_user_id=manager.id
            )
            repeated_close = await event_attendance_service.close_confirmation(
                session, event.id, actor_user_id=manager.id
            )
            assert closed.confirmation_open is False
            assert repeated_close.confirmation_closed_at == closed.confirmation_closed_at
            state = await event_attendance_service.participant_state(session, event.id, participant.id)
            assert state.confirmation_closed is True
            assert state.confirmation_open is False
            assert registration.status == RegistrationStatus.REGISTERED
            with pytest.raises(ValueError, match="attendance_not_open"):
                await event_attendance_service.confirm_attendance(
                    session, event.id, participant.id, completed.session.attendance_code
                )
    finally:
        await engine.dispose()


def test_confirmation_window_closes_without_losing_history() -> None:
    asyncio.run(_confirmation_window_closes_without_losing_history())


async def _attendance_code_confirmation_applies_event_scoring_role_bonus() -> None:
    """confirm_attendance (the self-service code flow, the primary
    attendance path) now also applies the Event Scoring Profile role bonus
    -- Points/Ranks ToR phase 2."""
    from app.services.activity_metrics_service import get_metric
    from app.services.points_service import total_points
    from app.utils.constants import EventParticipantRole

    engine, factory = await _session_factory()
    try:
        async with factory() as session:
            manager, participant, _stranger, event, registration = await _seed_event(session)
            registration.role = EventParticipantRole.ORGANIZER
            await session.flush()

            await event_attendance_service.start_event(
                session, event.id, actor_user_id=manager.id, bot=None, miniapp_url=""
            )
            completed = await event_attendance_service.complete_event(
                session, event.id, actor_user_id=manager.id, bot=None, miniapp_url=""
            )
            code = completed.session.attendance_code
            assert code is not None

            await event_attendance_service.confirm_attendance(session, event.id, participant.id, code)

            # base attendance (25, from _seed_event's points_for_visit) + organizer bonus (250)
            assert await total_points(session, participant.id) == 25 + 250
            assert await get_metric(session, user_id=participant.id, metric_key="events_attended") == 1
            assert await get_metric(session, user_id=participant.id, metric_key="events_organized") == 1

            # Repeat confirmation must not double-pay the role bonus either.
            await event_attendance_service.confirm_attendance(session, event.id, participant.id, code)
            assert await total_points(session, participant.id) == 25 + 250
    finally:
        await engine.dispose()


def test_attendance_code_confirmation_applies_event_scoring_role_bonus() -> None:
    asyncio.run(_attendance_code_confirmation_applies_event_scoring_role_bonus())


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


async def _qr_v2_uses_current_window_and_shared_ledger():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch
    from urllib.parse import urlparse, parse_qs
    from datetime import datetime, timezone
    from aiogram.filters import CommandObject
    from aiogram.types import Chat, Message, User as TelegramUser
    from app.config import Settings
    from app.handlers.emergency import rescue_start
    from app.services.event_qr_service import qr_png as legacy_qr_png
    engine, factory = await _session_factory()
    settings = Settings(bot_token='1234567890:test-token', feature_attendance_qr='ALL', bot_username='ERA_1bot')
    try:
        async with factory() as session:
            manager, participant, stranger, event, _registration = await _seed_event(session)
            with pytest.raises(ValueError, match='attendance_not_open'):
                await event_attendance_service.confirmation_qr(session, event.id, settings=settings, telegram_id=manager.telegram_id)
            await event_attendance_service.start_event(session, event.id, actor_user_id=manager.id, bot=None, miniapp_url='')
            await event_attendance_service.complete_event(session, event.id, actor_user_id=manager.id, bot=None, miniapp_url='')
            await session.commit()
            link, image = await event_attendance_service.confirmation_qr(session, event.id, settings=settings, telegram_id=manager.telegram_id)
            assert image.startswith(b'\x89PNG\r\n\x1a\n') and len(image) > 300
            payload = parse_qs(urlparse(link).query)['start'][0]
            parsed = event_attendance_service.parse_confirmation_payload(payload)
            assert parsed and parsed[0] == event.id and len(parsed[1]) == 8
            with pytest.raises(ValueError, match='not_registered'):
                await event_attendance_service.confirm_attendance(session, event.id, stranger.id, parsed[1])
            with pytest.raises(RuntimeError, match='retired'):
                legacy_qr_png(link)
        actor = TelegramUser(id=participant.telegram_id, first_name='Участник', is_bot=False)
        message = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=actor.id, type='private'), from_user=actor)
        with patch('app.handlers.emergency._subscription_ok', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=AsyncMock()) as answer:
            for _ in range(2):
                async with factory() as session:
                    user = await session.get(User, participant.id)
                    await rescue_start(message, SimpleNamespace(), user, settings, SimpleNamespace(clear=AsyncMock()), session,
                                       command=CommandObject(prefix='/', command='start', args=payload))
            assert 'уже подтверждено' in answer.await_args.args[0]
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(PointTransaction).where(PointTransaction.user_id == participant.id, PointTransaction.source_type == 'event_attendance')) == 1
            await event_attendance_service.close_confirmation(session, event.id, actor_user_id=manager.id)
            await session.commit()
            with pytest.raises(ValueError, match='attendance_not_open'):
                await event_attendance_service.confirmation_qr(session, event.id, settings=settings, telegram_id=manager.telegram_id)
    finally:
        await engine.dispose()


def test_qr_v2_uses_current_window_and_shared_ledger():
    asyncio.run(_qr_v2_uses_current_window_and_shared_ledger())


async def _native_code_uses_same_attendance_and_old_reminder_cannot_erase_it():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.config import Settings
    from app.handlers.participant.events_stability_block8 import confirmation_code_submit
    from app.handlers.participant.events import attendance_confirmation
    engine, factory = await _session_factory()
    try:
        async with factory() as session:
            manager, participant, _, event, registration = await _seed_event(session)
            await event_attendance_service.start_event(session, event.id, actor_user_id=manager.id, bot=None, miniapp_url='')
            result = await event_attendance_service.complete_event(session, event.id, actor_user_id=manager.id, bot=None, miniapp_url='')
            await session.commit()
            message = SimpleNamespace(from_user=SimpleNamespace(id=participant.telegram_id), text=result.session.attendance_code, answer=AsyncMock())
            state = SimpleNamespace(get_data=AsyncMock(return_value={'attendance_event_id': event.id}), clear=AsyncMock())
            settings = Settings(bot_token='1234567890:test-token', feature_attendance_qr='ALL')
            await confirmation_code_submit(message, participant, settings, session, state)
            assert 'Посещение подтверждено' in message.answer.await_args.args[0]
            call = SimpleNamespace(data=f'attendance:{event.id}:no', answer=AsyncMock(), message=message)
            await attendance_confirmation(call, participant, session)
            await session.commit()
            await session.refresh(registration)
            assert registration.status == RegistrationStatus.ATTENDED
            assert await session.scalar(select(func.count()).select_from(PointTransaction).where(PointTransaction.source_type == 'event_attendance')) == 1
    finally:
        await engine.dispose()


def test_native_code_uses_same_attendance_and_old_reminder_cannot_erase_it():
    asyncio.run(_native_code_uses_same_attendance_and_old_reminder_cannot_erase_it())


async def _lifecycle_notices_wait_for_commit_and_recover_without_duplicates():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch
    from app.config import Settings
    from app.database.models import AppSetting
    from app.database.system_models import NotificationDelivery
    engine, factory = await _session_factory()
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=20)))
    settings = Settings(bot_token='1234567890:test-token')
    try:
        async with factory() as session:
            manager, participant, _, event, _ = await _seed_event(session)
            event_id, manager_id = event.id, manager.id
            await event_attendance_service.start_event(session, event_id, actor_user_id=manager_id, bot=bot, miniapp_url='')
            bot.send_message.assert_not_awaited()
            await session.rollback()
        with patch('app.services.notification_service._session_factory', return_value=factory):
            assert await event_attendance_service.deliver_attendance_notifications(bot, settings, factory) == 0
            async with factory() as session:
                assert await session.scalar(select(AppSetting.key).where(AppSetting.key.like('event-lifecycle:%'))) is None
                await event_attendance_service.start_event(session, event_id, actor_user_id=manager_id, bot=bot, miniapp_url='')
                await session.commit()
            assert await event_attendance_service.deliver_attendance_notifications(bot, settings, factory) == 1
            assert await event_attendance_service.deliver_attendance_notifications(bot, settings, factory) == 0
            async with factory() as session:
                await event_attendance_service.complete_event(session, event_id, actor_user_id=manager_id, bot=bot, miniapp_url='')
                await session.commit()
            # Simulate a worker dying after common ledger acceptance, before the domain marker commit.
            sender = event_attendance_service.safe_send_once
            async def sent_then_crash(*args, **kwargs):
                await sender(*args, **kwargs)
                raise RuntimeError('simulated outbox crash')
            with patch.object(event_attendance_service, 'safe_send_once', side_effect=sent_then_crash):
                with pytest.raises(RuntimeError):
                    await event_attendance_service.deliver_attendance_notifications(bot, settings, factory)
            assert await event_attendance_service.deliver_attendance_notifications(bot, settings, factory) == 0
            assert bot.send_message.await_count == 2
            async with factory() as session:
                receipts = (await session.scalars(select(NotificationDelivery))).all()
                assert len(receipts) == 2 and all(row.status == 'sent' and row.attempt_count == 1 for row in receipts)
                assert await session.scalar(select(func.count()).select_from(AppSetting).where(AppSetting.key.like('event-lifecycle:pending:%'))) == 0
            from unittest.mock import Mock
            counted_factory = Mock(side_effect=factory)
            assert await event_attendance_service.deliver_attendance_notifications(bot, settings, counted_factory) == 0
            assert counted_factory.call_count == 1  # no sessions/locks for historical terminal rows
    finally:
        await engine.dispose()


def test_lifecycle_notices_wait_for_commit_and_recover_without_duplicates():
    asyncio.run(_lifecycle_notices_wait_for_commit_and_recover_without_duplicates())


async def _qr_handler_checks_manager_permission_before_reading_code():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch
    from app.config import Settings
    from app.handlers.admin.events_block6 import event_confirmation_qr
    user = SimpleNamespace(telegram_id=22, role=Role.PARTICIPANT, is_blocked=False, is_archived=False, permission_grants=[])
    call = SimpleNamespace(data='admin:event:confirm_qr:1', from_user=SimpleNamespace(id=22), answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()))
    with patch('app.services.event_attendance_service.confirmation_qr', new=AsyncMock()) as qr:
        await event_confirmation_qr(call, user, Settings(bot_token='1234567890:test-token', feature_attendance_qr='ALL'), SimpleNamespace())
        qr.assert_not_awaited()


def test_qr_handler_checks_manager_permission_before_reading_code():
    asyncio.run(_qr_handler_checks_manager_permission_before_reading_code())


def test_qr_and_report_flags_default_and_blank_values_fail_closed():
    from app.config import Settings
    settings = Settings(bot_token='1234567890:test-token', feature_attendance_qr='', feature_management_reports='')
    assert settings.feature_attendance_qr == settings.feature_management_reports == 'OFF'
    assert not event_attendance_service.attendance_v2_enabled(settings, 22)
    settings.feature_attendance_qr = 'TESTERS'
    settings.attendance_qr_tester_ids = [11]
    assert event_attendance_service.attendance_v2_enabled(settings, 11)
    assert not event_attendance_service.attendance_v2_enabled(settings, 22)
