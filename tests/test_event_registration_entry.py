"""Registration entry from channel/topic/project/bot/Mini App links.

Real (isolated) database rows, mocked Telegram. No real chats are touched.
"""
import asyncio
import inspect
import os
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase, skipUnless
from unittest.mock import AsyncMock, patch

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import AppSetting, Event, EventRegistration, User
from app.handlers.event_registration_link import open_event_registration
from app.handlers.participant import events_stability_block8 as events
from app.handlers.participant.events_stability_block8 import event_join, event_view
from app.services import anniversary_registration_service as rsvp
from app.services import event_entry_service as entry
from app.services.event_service import _lock_event_for_capacity, register_for_event
from app.utils import texts
from app.utils.constants import ApplicationStatus, EventStatus, RegistrationStatus

PENDING_TEXT = texts.APPLICATION_PENDING


def _buttons(markup):
    if markup is None:
        return []
    return [button for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for button in _buttons(markup)]


class _Base(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.addAsyncCleanup(self.engine.dispose)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.factory() as session:
            owner = User(telegram_id=1, first_name="Орг", application_status=ApplicationStatus.APPROVED)
            session.add(owner)
            await session.flush()
            self.owner_id = owner.id
            event = Event(
                title="Весенний форум", description="Описание форума",
                event_date=date.today() + timedelta(days=5), event_time=time(18, 30),
                location="Дом Москвы", format="Очно", created_by=owner.id,
                participant_limit=1, status=EventStatus.REGISTRATION_OPEN,
            )
            session.add(event)
            await session.flush()
            self.event_id = event.id
            await session.commit()

    async def make_user(self, telegram_id, status=ApplicationStatus.APPROVED, **extra):
        async with self.factory() as session:
            user = User(telegram_id=telegram_id, first_name=f"U{telegram_id}", application_status=status, **extra)
            session.add(user)
            await session.commit()
            return user.id

    def message(self):
        return SimpleNamespace(answer=AsyncMock(), edit_reply_markup=AsyncMock(), reply_markup=None)

    async def open_card(self, user, telegram_id, **kwargs):
        message = self.message()
        async with self.factory() as session:
            await events.show_public_event_registration_card(
                message, user, session, kwargs.pop("event_id", self.event_id),
                telegram_id=telegram_id, **kwargs,
            )
            await session.commit()
        return message

    async def stored_intent(self, telegram_id):
        async with self.factory() as session:
            return await entry.remembered_event_id(session, telegram_id)

    async def registrations(self):
        async with self.factory() as session:
            return list(await session.scalars(
                select(EventRegistration).where(EventRegistration.event_id == self.event_id)
                .order_by(EventRegistration.id)
            ))

    def join_call(self, tg_id, event_id=None, message=None):
        return SimpleNamespace(
            data=f"event:join:{event_id or self.event_id}", answer=AsyncMock(),
            from_user=SimpleNamespace(id=tg_id), message=message or self.message(),
        )

    async def join(self, user_id, tg_id, message=None):
        call = self.join_call(tg_id, message=message)
        async with self.factory() as session:
            user = await session.get(User, user_id)
            await event_join(call, user, session)
        return call


class NewcomerEntryTests(_Base):
    async def test_newcomer_sees_title_date_and_application_button_and_event_is_remembered(self):
        message = await self.open_card(None, 900)
        message.answer.assert_awaited_once()
        text = message.answer.call_args.args[0]
        markup = message.answer.call_args.kwargs["reply_markup"]
        self.assertIn("Весенний форум", text)
        self.assertIn(f"{date.today() + timedelta(days=5):%d.%m.%Y}", text)
        self.assertIn("18:30", text)
        self.assertIn("анкету", text)
        self.assertEqual(_callbacks(markup), ["registration:start"])
        self.assertEqual(await self.stored_intent(900), self.event_id)

    async def test_newcomer_with_unfinished_application_draft_gets_resume_button(self):
        message = await self.open_card(None, 900, resume_registration=True)
        self.assertEqual(_callbacks(message.answer.call_args.kwargs["reply_markup"]), ["registration:resume"])

    async def test_newcomer_cannot_register_or_see_participant_counters(self):
        message = await self.open_card(None, 900)
        self.assertNotIn("Свободных мест", message.answer.call_args.args[0])
        self.assertNotIn(f"event:join:{self.event_id}", _callbacks(message.answer.call_args.kwargs["reply_markup"]))
        self.assertEqual(await self.registrations(), [])

    async def test_newcomer_draft_or_unknown_event_fails_closed_and_is_not_remembered(self):
        async with self.factory() as session:
            event = await session.get(Event, self.event_id)
            event.status = EventStatus.DRAFT
            await session.commit()
        for event_id in (self.event_id, 987654):
            message = await self.open_card(None, 901, event_id=event_id)
            self.assertIn("недоступно", message.answer.call_args.args[0])
        self.assertIsNone(await self.stored_intent(901))

    async def test_repeat_open_keeps_a_single_remembered_event_row(self):
        await self.open_card(None, 900)
        await self.open_card(None, 900)
        async with self.factory() as session:
            count = await session.scalar(select(func.count()).select_from(AppSetting).where(
                AppSetting.key == entry.intent_key(900)))
        self.assertEqual(count, 1)

    async def test_stale_join_button_for_newcomer_opens_entry_card_not_dead_end(self):
        call = self.join_call(902)
        async with self.factory() as session:
            await event_join(call, None, session)
            await session.commit()
        call.message.answer.assert_awaited_once()
        self.assertIn("Весенний форум", call.message.answer.call_args.args[0])
        self.assertEqual(await self.stored_intent(902), self.event_id)
        self.assertEqual(await self.registrations(), [])

    async def test_old_event_view_callback_for_newcomer_opens_same_entry(self):
        call = SimpleNamespace(
            data=f"event:view:{self.event_id}", answer=AsyncMock(),
            from_user=SimpleNamespace(id=903), message=self.message(),
        )
        async with self.factory() as session:
            await event_view(call, None, session)
            await session.commit()
        self.assertIn("Весенний форум", call.message.answer.call_args.args[0])
        self.assertEqual(await self.stored_intent(903), self.event_id)


class ApplicantStatusTests(_Base):
    async def test_applicant_sees_real_status_and_event_is_remembered(self):
        cases = [
            (ApplicationStatus.PENDING, "на рассмотрении", ["registration:status"], True),
            (ApplicationStatus.NEEDS_INFO, "нужно уточнение", ["registration:reapply", "registration:status"], True),
            (ApplicationStatus.REJECTED, "не одобрена", ["registration:reapply", "registration:status"], True),
        ]
        for index, (status, fragment, callbacks, remembered) in enumerate(cases):
            with self.subTest(status=status):
                tg = 700 + index
                await self.make_user(tg, status)
                async with self.factory() as session:
                    user = await session.scalar(select(User).where(User.telegram_id == tg))
                message = await self.open_card(user, tg)
                text = message.answer.call_args.args[0]
                self.assertIn("Весенний форум", text)
                self.assertIn(fragment, text)
                self.assertEqual(_callbacks(message.answer.call_args.kwargs["reply_markup"]), callbacks)
                self.assertEqual(await self.stored_intent(tg), self.event_id if remembered else None)

    async def test_rejected_applicant_is_not_promised_a_return(self):
        await self.make_user(710, ApplicationStatus.REJECTED)
        async with self.factory() as session:
            user = await session.scalar(select(User).where(User.telegram_id == 710))
        message = await self.open_card(user, 710)
        self.assertNotIn("пришлёт кнопку", message.answer.call_args.args[0])

    async def test_blocked_or_archived_applicant_fails_closed(self):
        for index, flags in enumerate(({"is_blocked": True}, {"is_archived": True})):
            tg = 720 + index
            await self.make_user(tg, ApplicationStatus.APPROVED, **flags)
            async with self.factory() as session:
                user = await session.scalar(select(User).where(User.telegram_id == tg))
            message = await self.open_card(user, tg)
            message.answer.assert_awaited_once_with(PENDING_TEXT)
            self.assertIsNone(await self.stored_intent(tg))
            call = self.join_call(tg)
            async with self.factory() as session:
                await event_join(call, user, session)
            call.message.answer.assert_awaited_once_with(PENDING_TEXT)
        self.assertEqual(await self.registrations(), [])


class ReturnToEventTests(_Base):
    async def test_registration_followup_remembers_event_for_pending_application(self):
        async with self.factory() as session:
            await entry.remember_event(session, 800, self.event_id)
            await session.commit()
        async with self.factory() as session:
            text, markup = await entry.registration_followup(session, 800, approved=False)
        self.assertIn("Весенний форум", text)
        self.assertIsNone(markup)
        async with self.factory() as session:
            text, markup = await entry.registration_followup(session, 800, approved=True)
        self.assertEqual(_callbacks(markup), [f"event:view:{self.event_id}"])

    async def test_no_followup_without_event_or_for_unpublished_event(self):
        async with self.factory() as session:
            self.assertIsNone(await entry.registration_followup(session, 801, approved=False))
            await entry.remember_event(session, 801, self.event_id)
            event = await session.get(Event, self.event_id)
            event.status = EventStatus.CANCELLED
            await session.commit()
        async with self.factory() as session:
            self.assertIsNone(await entry.registration_followup(session, 801, approved=False))

    async def test_remembered_event_expires(self):
        async with self.factory() as session:
            await entry.remember_event(session, 802, self.event_id)
            await session.commit()
            later = datetime.now(timezone.utc) + entry.INTENT_TTL + timedelta(minutes=1)
            self.assertIsNone(await entry.remembered_event_id(session, 802, now=later))

    async def test_approval_notice_carries_button_back_to_the_event(self):
        from app.keyboards.participant import main_inline_keyboard
        async with self.factory() as session:
            await entry.remember_event(session, 803, self.event_id)
            await session.commit()
        async with self.factory() as session:
            base = main_inline_keyboard(miniapp_url="https://example.invalid/app")
            markup = await entry.with_pending_event_button(session, 803, base)
            plain = await entry.with_pending_event_button(session, 804, base)
        self.assertEqual(_buttons(markup)[0].callback_data, f"event:view:{self.event_id}")
        self.assertEqual(len(_buttons(markup)), len(_buttons(base)) + 1)
        self.assertEqual(_callbacks(plain), _callbacks(base))

    async def test_staged_approval_notice_delivery_includes_event_button(self):
        from app.services import application_review_service as review
        user_id = await self.make_user(805, ApplicationStatus.PENDING)
        async with self.factory() as session:
            await entry.remember_event(session, 805, self.event_id)
            target = await session.get(User, user_id)
            await review.approve_application(session, target, actor_id=self.owner_id)
            key = await review.stage_application_notice(session, target, text="Одобрено")
            await session.commit()
        sent = {}

        async def fake_send_once(bot, settings, chat_id, text, **kwargs):
            sent.update(chat_id=chat_id, markup=kwargs.get("reply_markup"))
            return SimpleNamespace(status="sent", error_code=None, attempt_count=1)

        settings = SimpleNamespace(effective_miniapp_url="https://example.invalid/app")
        with (
            patch("app.services.notification_service.safe_send_once", new=fake_send_once),
            patch("app.services.chat_access_service.sync_user_chat_access",
                  new=AsyncMock(return_value=(None, False))),
        ):
            await review.deliver_application_notices(object(), settings, self.factory, only_key=key)
        self.assertEqual(sent["chat_id"], 805)
        self.assertIn(f"event:view:{self.event_id}", _callbacks(sent["markup"]))

    async def test_approved_user_arrives_at_full_card_and_pending_event_is_cleared(self):
        user_id = await self.make_user(806, ApplicationStatus.APPROVED)
        async with self.factory() as session:
            await entry.remember_event(session, 806, self.event_id)
            await session.commit()
            user = await session.get(User, user_id)
        message = await self.open_card(user, 806)
        markup = message.answer.call_args.kwargs["reply_markup"]
        self.assertIn(f"event:join:{self.event_id}", _callbacks(markup))
        self.assertIn("Свободных мест", message.answer.call_args.args[0])
        self.assertIsNone(await self.stored_intent(806))

    async def test_opening_another_event_keeps_unrelated_pending_event(self):
        user_id = await self.make_user(807, ApplicationStatus.APPROVED)
        async with self.factory() as session:
            await entry.remember_event(session, 807, self.event_id + 100)
            await session.commit()
            user = await session.get(User, user_id)
        await self.open_card(user, 807)
        async with self.factory() as session:
            self.assertEqual(await entry.remembered_event_id(session, 807), self.event_id + 100)

    async def test_start_handler_keeps_unfinished_application_draft(self):
        state = SimpleNamespace(
            get_state=AsyncMock(return_value="RegistrationStates:email"), clear=AsyncMock())
        message = self.message()
        message.from_user = SimpleNamespace(id=808)
        command = SimpleNamespace(args=f"event_{self.event_id}")
        async with self.factory() as session:
            await open_event_registration(message, command, state, None, session, SimpleNamespace())
            await session.commit()
        state.clear.assert_not_awaited()
        self.assertEqual(_callbacks(message.answer.call_args.kwargs["reply_markup"]), ["registration:resume"])

    async def test_start_handler_clears_unrelated_state_for_approved_member(self):
        user_id = await self.make_user(809, ApplicationStatus.APPROVED)
        state = SimpleNamespace(get_state=AsyncMock(return_value="TaskStates:text"), clear=AsyncMock())
        message = self.message()
        message.from_user = SimpleNamespace(id=809)
        async with self.factory() as session:
            user = await session.get(User, user_id)
            await open_event_registration(
                message, SimpleNamespace(args=f"event_{self.event_id}"), state, user, session, SimpleNamespace(),
            )
        state.clear.assert_awaited_once()


class JoinResultTests(_Base):
    async def test_join_shows_result_and_replaces_join_button(self):
        user_id = await self.make_user(10)
        card = self.message()
        card.reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Зарегистрироваться", callback_data=f"event:join:{self.event_id}")],
            [InlineKeyboardButton(text="← Афиша", callback_data="events:list")],
        ])
        call = await self.join(user_id, 10, message=card)
        self.assertEqual(len(await self.registrations()), 1)
        shown = " ".join(str(c.args[0]) for c in call.message.answer.await_args_list)
        self.assertIn("Весенний форум", shown)
        card.edit_reply_markup.assert_awaited_once()
        callbacks = _callbacks(card.edit_reply_markup.call_args.kwargs["reply_markup"])
        self.assertNotIn(f"event:join:{self.event_id}", callbacks)
        self.assertIn(f"event:plans_changed:{self.event_id}", callbacks)

    async def test_double_tap_is_idempotent_single_row(self):
        user_id = await self.make_user(11)
        await self.join(user_id, 11)
        second = await self.join(user_id, 11)
        self.assertEqual(len(await self.registrations()), 1)
        self.assertIn("уже", second.message.answer.call_args.args[0].lower())

    async def test_last_seat_goes_to_first_and_second_is_told_event_is_full(self):
        first, second = await self.make_user(12), await self.make_user(13)
        await self.join(first, 12)
        call = await self.join(second, 13)
        rows = await self.registrations()
        self.assertEqual([row.status for row in rows], [RegistrationStatus.REGISTERED])
        self.assertIn("мест", call.message.answer.call_args.args[0])

    async def test_full_event_with_waitlist_enabled_puts_second_user_on_waitlist(self):
        async with self.factory() as session:
            session.add(EventExperience(event_id=self.event_id, waitlist_enabled=True))
            await session.commit()
        first, second = await self.make_user(14), await self.make_user(15)
        await self.join(first, 14)
        call = await self.join(second, 15)
        self.assertEqual(
            sorted(row.status for row in await self.registrations()),
            sorted([RegistrationStatus.REGISTERED, RegistrationStatus.WAITLIST]),
        )
        self.assertIn("лист", " ".join(str(c.args[0]) for c in call.message.answer.await_args_list).lower())

    async def test_closed_registration_and_not_required_events_do_not_register(self):
        user_id = await self.make_user(16)
        async with self.factory() as session:
            session.add(EventExperience(
                event_id=self.event_id, registration_close_at=datetime.now(timezone.utc) - timedelta(hours=1)))
            await session.commit()
        call = await self.join(user_id, 16)
        self.assertIn("закрыта", call.message.answer.call_args.args[0])
        async with self.factory() as session:
            experience = await session.get(EventExperience, self.event_id)
            experience.registration_close_at = None
            experience.registration_required = False
            await session.commit()
        call = await self.join(user_id, 16)
        self.assertIn("не нужна", call.message.answer.call_args.args[0])
        self.assertEqual(await self.registrations(), [])

    async def test_cancel_frees_the_seat_for_the_next_person(self):
        first, second = await self.make_user(17), await self.make_user(18)
        await self.join(first, 17)
        async with self.factory() as session:
            event = await session.get(Event, self.event_id)
            row = (await self.registrations())[0]
            stored = await session.get(EventRegistration, row.id)
            stored.status = RegistrationStatus.CANCELLED
            await session.commit()
        call = await self.join(second, 18)
        statuses = {r.user_id: r.status for r in await self.registrations()}
        self.assertEqual(statuses[second], RegistrationStatus.REGISTERED)
        self.assertEqual(statuses[first], RegistrationStatus.CANCELLED)
        self.assertIsNotNone(event)
        call.message.answer.assert_awaited()


class SeatConcurrencyTests(_Base):
    def test_capacity_lock_is_a_row_lock_on_postgresql(self):
        from sqlalchemy.dialects import postgresql
        source = inspect.getsource(_lock_event_for_capacity)
        self.assertIn("with_for_update", source)
        statement = select(Event).where(Event.id == 1).with_for_update()
        self.assertIn("FOR UPDATE", str(statement.compile(dialect=postgresql.dialect())))

    @skipUnless(os.getenv("ERA_TEST_PG_URL"), "set ERA_TEST_PG_URL to a PostgreSQL database")
    async def test_users_race_for_single_seat_on_postgresql(self):
        # SQLite has no row locks, so only PostgreSQL proves the single-seat guarantee.
        # The tables live in a throw-away schema; existing data is never touched.
        url = os.environ["ERA_TEST_PG_URL"]
        schema = f"era_seat_race_{uuid.uuid4().hex[:12]}"
        admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
        self.addAsyncCleanup(admin.dispose)
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

        async def drop_schema():
            async with admin.connect() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))

        self.addAsyncCleanup(drop_schema)
        engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
        self.addAsyncCleanup(engine.dispose)
        await self._race(engine, users=6)

    async def _race(self, engine, users=2):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            owner = User(telegram_id=1, first_name="Орг", application_status=ApplicationStatus.APPROVED)
            people = [User(telegram_id=100 + i, first_name=f"P{i}", application_status=ApplicationStatus.APPROVED)
                      for i in range(users)]
            session.add_all([owner, *people])
            await session.flush()
            event = Event(
                title="Гонка", description="d", event_date=date.today() + timedelta(days=2),
                event_time=time(10), location="L", format="Очно", created_by=owner.id,
                participant_limit=1, status=EventStatus.REGISTRATION_OPEN)
            session.add(event)
            await session.flush()
            event_id, ids = event.id, [p.id for p in people]
            await session.commit()

        async def attempt(user_id):
            async with factory() as session:
                try:
                    event = await session.get(Event, event_id)
                    _, error = await register_for_event(session, event, user_id)
                    await session.commit()
                    return error
                except Exception as exc:  # SQLite may refuse the second writer outright
                    await session.rollback()
                    return f"db:{type(exc).__name__}"

        results = await asyncio.gather(*(attempt(user_id) for user_id in ids))
        async with factory() as session:
            seated = await session.scalar(select(func.count()).select_from(EventRegistration).where(
                EventRegistration.event_id == event_id,
                EventRegistration.status == RegistrationStatus.REGISTERED))
        self.assertEqual(seated, 1, results)
        self.assertEqual(results.count(None), 1, results)
        self.assertTrue(all(r in {None, "full"} or str(r).startswith("db:") for r in results), results)


class AnniversaryEntryTests(_Base):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with self.factory() as session:
            event = Event(
                title="Первая годовщина ЭРА — 1 ГОД", description="Приглашение",
                event_date=rsvp.START.date(), event_time=time(18), location="Дом Москвы в Ереване",
                format="Очно", created_by=self.owner_id, status=EventStatus.PUBLISHED, access_type="all",
                additional_info=rsvp.EVENT_MARKER)
            session.add(event)
            await session.flush()
            self.anniversary_id = event.id
            await session.commit()
        patcher = patch.object(rsvp, "registration_open", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_guest_without_profile_gets_anniversary_form_not_member_application(self):
        message = await self.open_card(None, 950, event_id=self.anniversary_id)
        callbacks = _callbacks(message.answer.call_args.kwargs["reply_markup"])
        self.assertEqual(callbacks, ["anniversary:begin"])
        self.assertIsNone(await self.stored_intent(950))

    async def test_pending_applicant_with_full_profile_uses_quick_anniversary_registration(self):
        await self.make_user(951, ApplicationStatus.PENDING, last_name="Иванова", education_work="ЭРА")
        async with self.factory() as session:
            user = await session.scalar(select(User).where(User.telegram_id == 951))
        message = await self.open_card(user, 951, event_id=self.anniversary_id)
        self.assertEqual(_callbacks(message.answer.call_args.kwargs["reply_markup"]), ["anniversary:quick"])

    async def test_approved_member_keeps_existing_anniversary_card_and_keyboard(self):
        user_id = await self.make_user(952, ApplicationStatus.APPROVED, last_name="Иванова", education_work="ЭРА")
        async with self.factory() as session:
            user = await session.get(User, user_id)
        message = await self.open_card(user, 952, event_id=self.anniversary_id)
        callbacks = _callbacks(message.answer.call_args.kwargs["reply_markup"])
        self.assertEqual(callbacks[0], "anniversary:quick")
        self.assertIn(f"event:calendar:{self.anniversary_id}", callbacks)

    async def test_registered_guest_sees_confirmation_instead_of_button(self):
        async with self.factory() as session:
            await rsvp.register(session, 953, {"first_name": "Гость", "last_name": "Тестов", "organization": "ЭРА"})
        message = await self.open_card(None, 953, event_id=self.anniversary_id)
        self.assertIn("Вы зарегистрированы", message.answer.call_args.args[0])
        self.assertIsNone(message.answer.call_args.kwargs["reply_markup"])

    async def test_blocked_user_cannot_reach_anniversary_through_entry(self):
        await self.make_user(954, ApplicationStatus.APPROVED, is_blocked=True)
        async with self.factory() as session:
            user = await session.scalar(select(User).where(User.telegram_id == 954))
        message = await self.open_card(user, 954, event_id=self.anniversary_id)
        message.answer.assert_awaited_once_with(PENDING_TEXT)

    async def test_registration_closed_shows_closed_state(self):
        with patch.object(rsvp, "registration_open", return_value=False):
            message = await self.open_card(None, 955, event_id=self.anniversary_id)
        self.assertIn("закрыта", message.answer.call_args.args[0])
        self.assertIsNone(message.answer.call_args.kwargs["reply_markup"])


class LinkContractTests(TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_published_links_and_old_buttons_keep_working(self):
        from app.utils.deep_links import (
            parse_event_registration_payload,
            telegram_event_miniapp_url,
            telegram_event_registration_url,
        )
        self.assertEqual(telegram_event_registration_url("ERA_1bot", 7), "https://t.me/ERA_1bot?start=event_7")
        self.assertEqual(parse_event_registration_payload("event_7"), 7)
        self.assertIn("startapp=event_7", telegram_event_miniapp_url("ERA_1bot", 7))

    def test_miniapp_start_param_and_project_card_open_event(self):
        app = (self.ROOT / "frontend/src/app/App.tsx").read_text()
        self.assertIn("[/^event_(\\d+)$/, (id) => `events/${id}`]", app)
        workspace = (self.ROOT / "frontend/src/screens/projects/ProjectWorkspace.tsx").read_text()
        self.assertRegex(workspace, re.compile(r"window\.location\.hash = `#/events/\$\{event\.id\}`"))
        self.assertIn("OPENABLE_EVENT_STATUSES", workspace)
