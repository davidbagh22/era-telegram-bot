"""Exercise event notices with a real, isolated transaction and mocked Telegram."""

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.sql.dml import Update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.events import cancel_event_registration, register_event
from app.config import Settings
from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import Event, EventRegistration, User
from app.database.system_models import NotificationDelivery
from app.handlers.participant.event_plans_changed import plans_changed
from app.handlers.participant.events_stability_block8 import event_join, event_view
from app.services.event_registration_notice_service import recover_event_registration_notices
from app.services.event_registration_policy import registration_is_closed
from app.services.event_service import register_for_event, send_committed_registration_notice
from app.services.points_service import total_points
from app.utils.constants import ApplicationStatus, EventStatus, RegistrationStatus


def test_registration_deadline_handles_legacy_utc_and_aware_offsets() -> None:
    now = datetime(2026, 11, 12, 18, tzinfo=timezone.utc)
    assert registration_is_closed(SimpleNamespace(registration_close_at=datetime(2026, 11, 12, 18)), now=now)
    later_in_yerevan = datetime(2026, 11, 12, 22, 1, tzinfo=timezone(timedelta(hours=4)))
    assert not registration_is_closed(SimpleNamespace(registration_close_at=later_in_yerevan), now=now)


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

    async def _receipts(self) -> list[NotificationDelivery]:
        async with self.sessions() as session:
            return list(await session.scalars(select(NotificationDelivery).order_by(NotificationDelivery.id)))

    async def _fill_event_and_waitlist(self) -> None:
        async with self.sessions() as session:
            for user_id, status in (
                (self.first_id, RegistrationStatus.REGISTERED),
                (self.second_id, RegistrationStatus.WAITLIST),
            ):
                user = await session.get(User, user_id)
                result = await register_event(self.event_id, user, session, None, self.settings)
                self.assertEqual(result.registration_status, status)
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
        self.assertEqual(await self._receipts(), [])
        async with self.sessions() as session:
            self.assertEqual(await total_points(session, self.first_id), 0)

    async def test_telegram_timeout_preserves_success_without_retry(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=TimeoutError("test Telegram timeout")))
        async with self.sessions() as session:
            user = await session.get(User, self.first_id)
            with self.assertLogs("app.services.event_registration_notice_service", level="ERROR"):
                result = await register_event(self.event_id, user, session, bot, self.settings)
        self.assertEqual(result.registration_status, RegistrationStatus.REGISTERED)
        self.assertEqual(await self._stored_status(self.first_id), RegistrationStatus.REGISTERED)
        await recover_event_registration_notices(bot, self.settings, self.sessions)
        bot.send_message.assert_awaited_once()
        receipt, = await self._receipts()
        self.assertEqual((receipt.status, receipt.attempt_count), ("uncertain", 1))

    async def test_registration_recovers_after_commit_and_sends_once(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=710)))
        async with self.sessions() as session:
            user = await session.get(User, self.first_id)
            with patch("app.api.v1.events.deliver_registration_notice", new=AsyncMock()):
                result = await register_event(self.event_id, user, session, bot, self.settings)
        self.assertEqual(result.registration_status, RegistrationStatus.REGISTERED)
        self.assertEqual(await self._stored_status(self.first_id), RegistrationStatus.REGISTERED)
        receipt, = await self._receipts()
        self.assertEqual((receipt.status, receipt.attempt_count), ("queued", 0))
        bot.send_message.assert_not_awaited()

        await recover_event_registration_notices(bot, self.settings, self.sessions)
        await recover_event_registration_notices(bot, self.settings, self.sessions)
        bot.send_message.assert_awaited_once()
        recipient, reply = bot.send_message.await_args.args
        self.assertEqual(recipient, 101)
        self.assertIn("Вы зарегистрированы", reply)
        receipt, = await self._receipts()
        self.assertEqual((receipt.status, receipt.message_id, receipt.attempt_count), ("sent", 710, 1))

    async def test_confirmed_send_with_failed_receipt_write_is_not_replayed(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=711)))
        async with self.sessions() as session:
            user = await session.get(User, self.first_id)
            execute = session.execute

            async def fail_receipt_write(statement, *args, **kwargs):
                if isinstance(statement, Update) and statement.table.name == NotificationDelivery.__tablename__:
                    raise RuntimeError("receipt store unavailable")
                return await execute(statement, *args, **kwargs)

            with (
                patch.object(session, "execute", side_effect=fail_receipt_write),
                self.assertLogs("app.services.event_registration_notice_service", level="ERROR"),
            ):
                result = await register_event(self.event_id, user, session, bot, self.settings)
        self.assertEqual(result.registration_status, RegistrationStatus.REGISTERED)
        async with self.sessions() as session, session.begin():
            receipt = await session.scalar(select(NotificationDelivery))
            self.assertEqual((receipt.status, receipt.attempt_count), ("pending", 1))
            receipt.last_attempt_at = datetime.now(timezone.utc) - timedelta(hours=1)

        await recover_event_registration_notices(bot, self.settings, self.sessions)
        bot.send_message.assert_awaited_once()
        receipt, = await self._receipts()
        self.assertEqual((receipt.status, receipt.error_code), ("uncertain", "delivery_outcome_unknown"))

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

    async def test_promoted_waitlist_member_receives_queued_notice_after_restart(self) -> None:
        await self._fill_event_and_waitlist()
        bot = SimpleNamespace(send_message=AsyncMock())
        async with self.sessions() as session:
            user = await session.get(User, self.first_id)
            with patch("app.api.v1.events.deliver_registration_notice", new=AsyncMock()):
                await cancel_event_registration(self.event_id, user, session, bot, self.settings)
        self.assertEqual(await self._stored_status(self.second_id), RegistrationStatus.REGISTERED)
        receipt, = await self._receipts()
        self.assertEqual((receipt.status, receipt.chat_id), ("queued", 102))

        await recover_event_registration_notices(bot, self.settings, self.sessions)
        await recover_event_registration_notices(bot, self.settings, self.sessions)
        bot.send_message.assert_awaited_once()
        recipient, reply = bot.send_message.await_args.args
        self.assertEqual(recipient, 102)
        self.assertIn("Для вас освободилось место", reply)

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
        self.assertEqual(await self._receipts(), [])

    async def test_queued_notice_is_skipped_when_event_is_no_longer_public(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock())
        for status in (EventStatus.DRAFT, EventStatus.PENDING_APPROVAL, EventStatus.CANCELLED):
            with self.subTest(status=status), patch("app.api.v1.events.deliver_registration_notice", new=AsyncMock()):
                async with self.sessions() as session:
                    event = await session.get(Event, self.event_id)
                    event.status = EventStatus.REGISTRATION_OPEN
                    await session.commit()
                    user = await session.get(User, self.first_id)
                    await register_event(self.event_id, user, session, bot, self.settings)
                    event.status = status
                    await session.commit()
                await recover_event_registration_notices(bot, self.settings, self.sessions)
                async with self.sessions() as session, session.begin():
                    registration = await session.scalar(select(EventRegistration))
                    registration.status = RegistrationStatus.NOT_COMING
        bot.send_message.assert_not_awaited()
        self.assertEqual([row.status for row in await self._receipts()], ["skipped"] * 3)

    async def test_reregistration_supersedes_an_unsent_confirmation(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock())
        async with self.sessions() as session:
            user = await session.get(User, self.first_id)
            with patch("app.api.v1.events.deliver_registration_notice", new=AsyncMock()):
                await register_event(self.event_id, user, session, bot, self.settings)
                await cancel_event_registration(self.event_id, user, session, bot, self.settings)
                await register_event(self.event_id, user, session, bot, self.settings)
        self.assertEqual([row.status for row in await self._receipts()], ["queued", "queued"])
        await recover_event_registration_notices(bot, self.settings, self.sessions)
        bot.send_message.assert_awaited_once()
        self.assertEqual([row.status for row in await self._receipts()], ["skipped", "sent"])

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
        self.assertEqual(await self._receipts(), [])

    async def test_native_waitlist_notice_recovers_in_private_chat(self) -> None:
        async with self.sessions() as session:
            first = await session.get(User, self.first_id)
            await register_event(self.event_id, first, session, None, self.settings)
            second = await session.get(User, self.second_id)
            call = self._event_callback("join")
            with patch("app.handlers.participant.events_stability_block8.deliver_registration_notice", new=AsyncMock()):
                await event_join(call, second, session)
        call.message.answer.assert_not_awaited()
        self.assertEqual(await self._stored_status(self.second_id), RegistrationStatus.WAITLIST)
        bot = SimpleNamespace(send_message=AsyncMock())
        await recover_event_registration_notices(bot, self.settings, self.sessions)
        bot.send_message.assert_awaited_once()
        recipient, reply = bot.send_message.await_args.args
        self.assertEqual(recipient, 102)
        self.assertIn("Вы в листе ожидания", reply)

    def _event_callback(self, action: str) -> SimpleNamespace:
        return SimpleNamespace(
            data=f"event:{action}:{self.event_id}", answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )

    async def _native_join_buttons(self, user: User, session) -> list[str]:
        with patch("app.handlers.participant.events_stability_block8.send_event_card", new=AsyncMock()) as card:
            await event_view(self._event_callback("view"), user, session)
        buttons = card.await_args.kwargs["keyboard"].inline_keyboard
        return [button.text for row in buttons for button in row if button.callback_data == f"event:join:{self.event_id}"]

    async def test_native_legacy_full_event_and_enabled_waitlist_use_correct_actions(self) -> None:
        async with self.sessions() as session:
            experience = await session.get(EventExperience, self.event_id)
            await session.delete(experience)
            event = await session.get(Event, self.event_id)
            _, error = await register_for_event(session, event, self.first_id)
            self.assertIsNone(error)
            await session.commit()

        for enabled in (False, True):
            with self.subTest(waitlist_enabled=enabled):
                async with self.sessions() as session:
                    if enabled:
                        session.add(EventExperience(event_id=self.event_id, waitlist_enabled=True))
                        await session.commit()
                    user = await session.get(User, self.second_id)
                    joins = await self._native_join_buttons(user, session)
                    self.assertEqual(joins, ["Встать в лист ожидания"] if enabled else [])
                    call = self._event_callback("join")
                    await event_join(call, user, session)
                    self.assertIn("в листе ожидания" if enabled else "Свободных мест", call.message.answer.await_args.args[0])
                expected = RegistrationStatus.WAITLIST if enabled else None
                self.assertEqual(await self._stored_status(self.second_id), expected)

        async with self.sessions() as session:
            user = await session.get(User, self.second_id)
            call = self._event_callback("join")
            await event_join(call, user, session)
            self.assertIn("уже в листе ожидания", call.message.answer.await_args.args[0])

    async def test_deadline_and_disabled_registration_reject_stale_callbacks_in_both_clients(self) -> None:
        expired = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
        for required, deadline, detail, reply in (
            (True, expired, "closed", "закрыта"),
            (False, None, "registration_not_required", "не нужна"),
        ):
            with self.subTest(detail=detail):
                async with self.sessions() as session:
                    experience = await session.get(EventExperience, self.event_id)
                    experience.registration_required = required
                    experience.registration_close_at = deadline
                    await session.commit()
                    user = await session.get(User, self.first_id)
                    with self.assertRaises(HTTPException) as error:
                        await register_event(self.event_id, user, session, None, self.settings)
                    self.assertEqual((error.exception.status_code, error.exception.detail), (409, detail))
                    await session.rollback()

                async with self.sessions() as session:
                    user = await session.get(User, self.first_id)
                    self.assertEqual(await self._native_join_buttons(user, session), [])
                    call = self._event_callback("join")
                    await event_join(call, user, session)
                    self.assertIn(reply, call.message.answer.await_args.args[0])
                self.assertIsNone(await self._stored_status(self.first_id))
