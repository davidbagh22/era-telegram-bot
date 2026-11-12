"""Exercise event notices with a real, isolated transaction and mocked Telegram."""

from datetime import date, time, timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.events import cancel_event_registration, register_event
from app.config import Settings
from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import Event, EventRegistration, User
from app.handlers.participant.event_plans_changed import plans_changed
from app.handlers.participant.events_stability_block8 import event_join
from app.services.event_service import register_for_event, send_committed_registration_notice
from app.services.points_service import total_points
from app.utils.constants import ApplicationStatus, EventStatus, RegistrationStatus


class EventCommitBeforeNotificationTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.addAsyncCleanup(self.engine.dispose)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token="0000000000:CITESTTOKEN")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with self.sessions() as session:
            first = User(telegram_id=101, first_name="First", application_status=ApplicationStatus.APPROVED)
            second = User(telegram_id=102, first_name="Second", application_status=ApplicationStatus.APPROVED)
            session.add_all([first, second])
            await session.flush()
            event = Event(
                title="Test event",
                description="Isolated registration fixture",
                event_date=date.today() + timedelta(days=3),
                event_time=time(18),
                location="Test venue",
                format="Offline",
                created_by=first.id,
                participant_limit=1,
                status=EventStatus.REGISTRATION_OPEN,
            )
            session.add(event)
            await session.flush()
            session.add(EventExperience(event_id=event.id, waitlist_enabled=True))
            await session.commit()
            self.event_id, self.first_id, self.second_id = event.id, first.id, second.id

    async def _stored_status(self, user_id: int) -> str | None:
        async with self.sessions() as session:
            return await session.scalar(
                select(EventRegistration.status).where(
                    EventRegistration.event_id == self.event_id,
                    EventRegistration.user_id == user_id,
                )
            )

    async def _fill_event_and_waitlist(self) -> None:
        async with self.sessions() as session:
            event = await session.get(Event, self.event_id)
            for user_id in (self.first_id, self.second_id):
                _, error = await register_for_event(session, event, user_id, waitlist_enabled=True)
                self.assertIsNone(error)
            await session.commit()
        self.assertEqual(await self._stored_status(self.second_id), RegistrationStatus.WAITLIST)

    async def test_api_confirmation_sees_committed_registration_and_retry_sends_nothing(self) -> None:
        observed = []
        async with self.sessions() as session:
            async def send(*args, **kwargs):
                observed.append((session.in_transaction(), await self._stored_status(self.first_id)))

            bot = SimpleNamespace(send_message=AsyncMock(side_effect=send))
            user = await session.get(User, self.first_id)
            result = await register_event(self.event_id, user, session, bot, self.settings)
            self.assertEqual(result.registration_status, RegistrationStatus.REGISTERED)
        self.assertEqual(observed, [(False, RegistrationStatus.REGISTERED)])

        async with self.sessions() as session:
            user = await session.get(User, self.first_id)
            with self.assertRaises(HTTPException) as error:
                await register_event(self.event_id, user, session, bot, self.settings)
            self.assertEqual((error.exception.status_code, error.exception.detail), (409, "already"))
        bot.send_message.assert_awaited_once()

    async def test_failed_registration_commit_rolls_back_registration_and_points(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock())
        async with self.sessions() as session:
            user = await session.get(User, self.first_id)
            with patch.object(session, "commit", new=AsyncMock(side_effect=RuntimeError("commit failed"))):
                with self.assertRaisesRegex(RuntimeError, "commit failed"):
                    await register_event(self.event_id, user, session, bot, self.settings)
        bot.send_message.assert_not_awaited()
        self.assertIsNone(await self._stored_status(self.first_id))
        async with self.sessions() as session:
            self.assertEqual(await total_points(session, self.first_id), 0)

    async def test_telegram_timeout_preserves_success_without_retry(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=TimeoutError("test Telegram timeout")))
        async with self.sessions() as session:
            user = await session.get(User, self.first_id)
            with self.assertLogs("app.services.event_service", level="ERROR"):
                result = await register_event(self.event_id, user, session, bot, self.settings)
        self.assertEqual(result.registration_status, RegistrationStatus.REGISTERED)
        self.assertEqual(await self._stored_status(self.first_id), RegistrationStatus.REGISTERED)
        bot.send_message.assert_awaited_once()

    async def test_promotion_notice_sees_committed_cancellation_and_promotion(self) -> None:
        await self._fill_event_and_waitlist()
        observed = []
        async with self.sessions() as session:
            async def send(chat_id, *args, **kwargs):
                observed.append((
                    chat_id,
                    session.in_transaction(),
                    await self._stored_status(self.first_id),
                    await self._stored_status(self.second_id),
                ))

            bot = SimpleNamespace(send_message=AsyncMock(side_effect=send))
            user = await session.get(User, self.first_id)
            result = await cancel_event_registration(self.event_id, user, session, bot, self.settings)
        self.assertEqual(result.registration_status, RegistrationStatus.NOT_COMING)
        self.assertEqual(observed, [(102, False, RegistrationStatus.NOT_COMING, RegistrationStatus.REGISTERED)])
        bot.send_message.assert_awaited_once()

    async def test_failed_cancellation_commit_preserves_both_statuses_and_skips_notice(self) -> None:
        await self._fill_event_and_waitlist()
        bot = SimpleNamespace(send_message=AsyncMock())
        async with self.sessions() as session:
            user = await session.get(User, self.first_id)
            with patch.object(session, "commit", new=AsyncMock(side_effect=RuntimeError("commit failed"))):
                with self.assertRaisesRegex(RuntimeError, "commit failed"):
                    await cancel_event_registration(self.event_id, user, session, bot, self.settings)
        bot.send_message.assert_not_awaited()
        self.assertEqual(await self._stored_status(self.first_id), RegistrationStatus.REGISTERED)
        self.assertEqual(await self._stored_status(self.second_id), RegistrationStatus.WAITLIST)

    async def test_stale_status_or_unavailable_event_suppresses_notice(self) -> None:
        async with self.sessions() as session:
            event = await session.get(Event, self.event_id)
            registration, error = await register_for_event(session, event, self.first_id)
            self.assertIsNone(error)
            registration_id = registration.id
            await session.commit()
            send = AsyncMock()
            await send_committed_registration_notice(session, registration_id, RegistrationStatus.WAITLIST, send)
            for status in (EventStatus.DRAFT, EventStatus.PENDING_APPROVAL, EventStatus.CANCELLED):
                with self.subTest(status=status):
                    event.status = status
                    await session.commit()
                    await send_committed_registration_notice(session, registration_id, RegistrationStatus.REGISTERED, send)
            send.assert_not_awaited()

    async def test_native_join_and_cancel_commit_before_reply(self) -> None:
        for prefix, handler, expected in (
            ("event:join", event_join, RegistrationStatus.REGISTERED),
            ("event:plans_changed", plans_changed, RegistrationStatus.NOT_COMING),
        ):
            observed = []
            async with self.sessions() as session:
                async def reply(*args, **kwargs):
                    observed.append((session.in_transaction(), await self._stored_status(self.first_id)))

                call = SimpleNamespace(
                    data=f"{prefix}:{self.event_id}", answer=AsyncMock(),
                    message=SimpleNamespace(answer=AsyncMock(side_effect=reply)),
                )
                user = await session.get(User, self.first_id)
                await handler(call, user, session)
                call.message.answer.assert_awaited_once()
            self.assertEqual(observed, [(False, expected)])

    async def test_native_join_failed_commit_skips_success_reply(self) -> None:
        call = SimpleNamespace(
            data=f"event:join:{self.event_id}", answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        async with self.sessions() as session:
            user = await session.get(User, self.first_id)
            with patch.object(session, "commit", new=AsyncMock(side_effect=RuntimeError("commit failed"))):
                with self.assertRaisesRegex(RuntimeError, "commit failed"):
                    await event_join(call, user, session)
        call.message.answer.assert_not_awaited()
        self.assertIsNone(await self._stored_status(self.first_id))
