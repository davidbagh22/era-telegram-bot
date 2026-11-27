"""Owner Excel after each new event registration — isolated DB, mocked Telegram."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from fastapi import HTTPException
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import GetMe
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.admin_event_operations import read_event_participants
from app.api.v1.events import register_event
from app.config import Settings
from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import Event, EventRegistration, User
from app.database.system_models import NotificationDelivery
from app.handlers.participant.events_stability_block8 import event_join
from app.services.event_owner_export_service import (
    NOTICE_TYPE,
    enqueue_owner_export,
    recover_owner_exports,
)
from app.services.event_participants_export import build_participants_xlsx
from app.utils.constants import ApplicationStatus, EventStatus, RegistrationStatus, Role

OWNER_TG = 900


def _sheet_rows(document) -> list[list[str]]:
    content = document.data if hasattr(document, "data") else document
    sheet = load_workbook(BytesIO(content)).active
    return [[str(cell or "") for cell in row] for row in sheet.iter_rows(values_only=True)]


class _OwnerExcelBase(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.addAsyncCleanup(self.engine.dispose)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with self.sessions() as session:
            owner = User(telegram_id=OWNER_TG, first_name="Владелец", application_status=ApplicationStatus.APPROVED, role=Role.ADMIN)
            anna = User(telegram_id=101, first_name="Анна", last_name="Тестова", application_status=ApplicationStatus.APPROVED)
            boris = User(telegram_id=102, first_name="Борис", last_name="Проверкин", application_status=ApplicationStatus.APPROVED)
            session.add_all([owner, anna, boris])
            await session.flush()
            event = Event(
                title="Тестовая встреча", description="Fixture", event_date=date.today() + timedelta(days=3),
                event_time=time(18), location="Тестовая площадка", format="Offline", created_by=owner.id,
                status=EventStatus.REGISTRATION_OPEN,
            )
            session.add(event)
            await session.flush()
            session.add(EventExperience(event_id=event.id, waitlist_enabled=True))
            await session.commit()
            self.event_id, self.owner_id = event.id, owner.id
            self.anna_id, self.boris_id = anna.id, boris.id
        self.settings = Settings(bot_token="0000000000:CITESTTOKEN", era_chair_user_id=self.owner_id)
        self.bot = SimpleNamespace(send_document=AsyncMock(), send_message=AsyncMock())

    def _call(self, bot=None):
        return SimpleNamespace(
            data=f"event:join:{self.event_id}", answer=AsyncMock(), bot=bot or self.bot,
            message=SimpleNamespace(answer=AsyncMock()),
        )

    async def _join_bot(self, user_id: int, bot=None, settings=None) -> None:
        async with self.sessions() as session:
            await event_join(self._call(bot), await session.get(User, user_id), session, settings or self.settings)

    async def _join_miniapp(self, user_id: int, bot=None, settings=None) -> None:
        async with self.sessions() as session:
            await register_event(self.event_id, await session.get(User, user_id), session, bot or self.bot, settings or self.settings)

    async def _rows(self) -> list[NotificationDelivery]:
        async with self.sessions() as session:
            return list(await session.scalars(
                select(NotificationDelivery).where(NotificationDelivery.notification_type == NOTICE_TYPE).order_by(NotificationDelivery.id)
            ))

    def _files(self) -> list[tuple[list[list[str]], str]]:
        return [
            (_sheet_rows(call.kwargs["document"]), call.kwargs["caption"])
            for call in self.bot.send_document.await_args_list
        ]

class OwnerExcelTests(_OwnerExcelBase):
    async def test_two_paths_send_two_files_matching_admin_list(self) -> None:
        await self._join_bot(self.anna_id)
        await self._join_miniapp(self.boris_id)

        files = self._files()
        self.assertEqual(len(files), 2)
        self.assertTrue(all(call.args[0] == OWNER_TG for call in self.bot.send_document.await_args_list))
        (first_rows, first_caption), (second_rows, second_caption) = files
        self.assertEqual([row[0] for row in first_rows[1:]], ["Анна"])
        self.assertEqual([row[0] for row in second_rows[1:]], ["Анна", "Борис"])
        self.assertIn("Тестовая встреча", first_caption)
        self.assertIn("Добавлен: Анна Тестова", first_caption)
        self.assertIn("Зарегистрировано: 1", first_caption)
        self.assertIn("Добавлен: Борис Проверкин", second_caption)
        self.assertIn("Зарегистрировано: 2", second_caption)

        async with self.sessions() as session:
            admin = await session.get(User, self.owner_id)
            listing = await read_event_participants(self.event_id, admin, session)
        self.assertEqual([item.first_name for item in listing], [row[0] for row in second_rows[1:]])
        self.assertEqual({row[5] for row in second_rows[1:]}, {"Зарегистрирован"})
        self.assertEqual(len(listing), len(second_rows) - 1)
        self.assertEqual({row.status for row in await self._rows()}, {"sent"})

    async def test_repeated_click_creates_no_row_and_no_third_file(self) -> None:
        await self._join_bot(self.anna_id)
        await self._join_miniapp(self.boris_id)
        await self._join_bot(self.anna_id)
        with self.assertRaises(HTTPException) as repeated:
            await self._join_miniapp(self.boris_id)
        self.assertEqual(repeated.exception.detail, "already")
        self.assertEqual(self.bot.send_document.await_count, 2)
        self.assertEqual(len(await self._rows()), 2)

    async def test_transient_failure_keeps_registration_and_retry_delivers(self) -> None:
        self.bot.send_document.side_effect = TelegramRetryAfter(GetMe(), "slow down", 1)
        await self._join_miniapp(self.anna_id)
        async with self.sessions() as session:
            status = await session.scalar(select(EventRegistration.status))
        self.assertEqual(status, RegistrationStatus.REGISTERED)
        rows = await self._rows()
        self.assertEqual([(row.status, row.error_code) for row in rows], [("queued", "telegram_retry_after")])

        self.bot.send_document.reset_mock(side_effect=True)
        await recover_owner_exports(self.bot, self.settings, self.sessions)
        self.assertEqual(self.bot.send_document.await_count, 1)
        self.assertEqual([row[0] for row in self._files()[0][0][1:]], ["Анна"])
        self.assertEqual([row.status for row in await self._rows()], ["sent"])
        await recover_owner_exports(self.bot, self.settings, self.sessions)
        self.assertEqual(self.bot.send_document.await_count, 1)

    async def test_uncertain_delivery_is_never_replayed(self) -> None:
        self.bot.send_document.side_effect = TelegramNetworkError(GetMe(), "timeout")
        await self._join_bot(self.anna_id)
        self.assertEqual([row.status for row in await self._rows()], ["uncertain"])
        self.bot.send_document.reset_mock(side_effect=True)
        await recover_owner_exports(self.bot, self.settings, self.sessions)
        self.bot.send_document.assert_not_awaited()
        await self._join_miniapp(self.boris_id)
        self.assertEqual([row[0] for row in self._files()[0][0][1:]], ["Анна", "Борис"])

    async def test_stale_entry_superseded_and_newest_file_names_everyone_added(self) -> None:
        offline = SimpleNamespace(send_document=AsyncMock(side_effect=TelegramRetryAfter(GetMe(), "x", 1)))
        # Both registrations commit; the first delivery is rate limited and the second never ran.
        await self._join_miniapp(self.anna_id, bot=offline)
        async with self.sessions() as session:
            user = await session.get(User, self.boris_id)
            event = await session.get(Event, self.event_id)
            from app.services.event_service import register_for_event
            registration, _error = await register_for_event(session, event, user.id)
            await enqueue_owner_export(session, self.settings, registration)
            await session.commit()

        await recover_owner_exports(self.bot, self.settings, self.sessions)
        self.assertEqual(self.bot.send_document.await_count, 1)
        rows, caption = self._files()[0]
        self.assertEqual([row[0] for row in rows[1:]], ["Анна", "Борис"])
        self.assertIn("Добавлены: Анна Тестова, Борис Проверкин", caption)
        stored = await self._rows()
        self.assertEqual([row.status for row in stored], ["skipped", "sent"])
        self.assertEqual(stored[0].error_code, "event_owner_export_superseded")
        await recover_owner_exports(self.bot, self.settings, self.sessions)
        self.assertEqual(self.bot.send_document.await_count, 1)

    async def test_newer_row_waits_for_in_flight_send_so_older_file_never_arrives_last(self) -> None:
        await self._join_bot(self.anna_id, bot=SimpleNamespace(send_document=AsyncMock(side_effect=TelegramRetryAfter(GetMe(), "x", 1))))
        async with self.sessions() as session:
            first = (await session.scalars(select(NotificationDelivery).where(NotificationDelivery.notification_type == NOTICE_TYPE))).one()
            first.status, first.last_attempt_at = "pending", datetime.now(timezone.utc)
            await session.commit()
        offline = SimpleNamespace(send_document=AsyncMock())
        await self._join_miniapp(self.boris_id, bot=offline)
        offline.send_document.assert_not_awaited()
        self.assertEqual([row.status for row in await self._rows()], ["pending", "queued"])

        async with self.sessions() as session:
            first = (await session.scalars(
                select(NotificationDelivery).where(NotificationDelivery.notification_type == NOTICE_TYPE).order_by(NotificationDelivery.id)
            )).first()
            first.status = "sent"
            await session.commit()
        await recover_owner_exports(self.bot, self.settings, self.sessions)
        self.assertEqual([row[0] for row in self._files()[0][0][1:]], ["Анна", "Борис"])
        self.assertEqual([row.status for row in await self._rows()], ["sent", "sent"])

    async def test_in_flight_sender_hands_over_to_the_deferred_newer_row(self) -> None:
        deferred = SimpleNamespace(send_document=AsyncMock())
        sent_snapshots: list[int] = []

        async def first_send(chat_id, document, caption):
            sent_snapshots.append(len(_sheet_rows(document)) - 1)
            if len(sent_snapshots) == 1:
                # Boris registers while Anna's file is still being sent.
                await self._join_miniapp(self.boris_id, bot=deferred)
            return SimpleNamespace(message_id=1)

        bot = SimpleNamespace(send_document=AsyncMock(side_effect=first_send), send_message=AsyncMock())
        await self._join_bot(self.anna_id, bot=bot)
        deferred.send_document.assert_not_awaited()
        self.assertEqual(sent_snapshots, [1, 2])
        self.assertEqual([row.status for row in await self._rows()], ["sent", "sent"])

    async def test_unresolved_owner_or_disabled_flag_fails_closed(self) -> None:
        cases = {
            "no owner": Settings(bot_token="0000000000:CITESTTOKEN"),
            "unknown telegram id": Settings(bot_token="0000000000:CITESTTOKEN", event_registration_owner_telegram_id=555),
            "disabled": Settings(bot_token="0000000000:CITESTTOKEN", era_chair_user_id=self.owner_id, event_registration_owner_excel_enabled=False),
        }
        for name, settings in cases.items():
            with self.subTest(name), self.assertLogs("app.services.event_owner_export_service", level=logging.WARNING) if name != "disabled" else _NullContext():
                async with self.sessions() as session:
                    session.add(EventRegistration(event_id=self.event_id, user_id=self.anna_id))
                    await session.flush()
                    registration = (await session.scalars(select(EventRegistration))).first()
                    self.assertIsNone(await enqueue_owner_export(session, settings, registration))
                    await session.rollback()
        self.assertEqual(await self._rows(), [])
        self.bot.send_document.assert_not_awaited()

    async def test_blocked_owner_account_is_not_a_recipient(self) -> None:
        async with self.sessions() as session:
            (await session.get(User, self.owner_id)).is_blocked = True
            await session.commit()
        await self._join_bot(self.anna_id)
        self.bot.send_document.assert_not_awaited()
        self.assertEqual(await self._rows(), [])

    async def test_explicit_owner_telegram_id_wins_over_chair(self) -> None:
        async with self.sessions() as session:
            session.add(User(telegram_id=777, first_name="Другой", application_status=ApplicationStatus.APPROVED))
            await session.commit()
        settings = Settings(bot_token="0000000000:CITESTTOKEN", era_chair_user_id=self.owner_id, event_registration_owner_telegram_id=777)
        await self._join_bot(self.anna_id, settings=settings)
        self.assertEqual(self.bot.send_document.await_args.args[0], 777)

    async def test_waitlist_registration_is_labelled_and_counted_separately(self) -> None:
        async with self.sessions() as session:
            (await session.get(Event, self.event_id)).participant_limit = 1
            await session.commit()
        await self._join_bot(self.anna_id)
        await self._join_miniapp(self.boris_id)
        rows, caption = self._files()[1]
        self.assertEqual([row[5] for row in rows[1:]], ["Зарегистрирован", "Лист ожидания"])
        self.assertIn("Борис Проверкин (лист ожидания)", caption)
        self.assertIn("Зарегистрировано: 1", caption)
        self.assertIn("В листе ожидания: 1", caption)

    async def test_builder_neutralises_formulas(self) -> None:
        async with self.sessions() as session:
            user = await session.get(User, self.anna_id)
            user.first_name = "=HYPERLINK(1)"
            registration = EventRegistration(event_id=self.event_id, user_id=user.id, status=RegistrationStatus.ATTENDED)
            registration.created_at = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
            document = build_participants_xlsx([(registration, user)], "Asia/Yerevan")
        rows = _sheet_rows(document)
        self.assertEqual(rows[1][0], "'=HYPERLINK(1)")
        self.assertEqual(rows[1][5:], ["Посетил", "27.11.2026 16:00"])


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class AdminBotScreenTests(_OwnerExcelBase):
    """The bot admin card: «Участники · N», newest first, groups, Excel."""

    async def _screen(self, handler, data: str):
        from app.handlers.admin import event_registration_block14 as module

        sent = SimpleNamespace(answer=AsyncMock(), answer_document=AsyncMock())
        call = SimpleNamespace(data=data, answer=AsyncMock(), message=sent, from_user=SimpleNamespace(id=OWNER_TG))
        async with self.sessions() as session:
            await getattr(module, handler)(call, await session.get(User, self.owner_id), self.settings, session)
        return sent

    async def test_card_button_shows_count_and_screen_is_newest_first_with_groups(self) -> None:
        from app.handlers.admin.events_block6 import event_kb

        async with self.sessions() as session:
            (await session.get(Event, self.event_id)).participant_limit = 1
            await session.commit()
        await self._join_bot(self.anna_id)
        await self._join_miniapp(self.boris_id)
        async with self.sessions() as session:
            event = await session.get(Event, self.event_id)
            texts = [row.text for line in event_kb(event, participants_count=1).inline_keyboard for row in line]
        self.assertIn("👥 Участники · 1", texts)

        sent = await self._screen("event_participants", f"admin:event:participants:{self.event_id}")
        text = sent.answer.await_args.args[0]
        self.assertIn("Участники · 1", text)
        self.assertLess(text.index("✅ Зарегистрированы"), text.index("⏳ Лист ожидания"))
        self.assertIn("Анна Тестова — Зарегистрирован", text)
        self.assertIn("Борис Проверкин — Лист ожидания", text)

    async def test_screen_lists_newest_registration_first(self) -> None:
        await self._join_bot(self.anna_id)
        await self._join_miniapp(self.boris_id)
        async with self.sessions() as session:
            first, second = await session.scalars(select(EventRegistration).order_by(EventRegistration.id))
            first.created_at = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
            second.created_at = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
            await session.commit()
        sent = await self._screen("event_participants", f"admin:event:participants:{self.event_id}")
        text = sent.answer.await_args.args[0]
        self.assertLess(text.index("Борис"), text.index("Анна"))

    async def test_excel_button_sends_the_shared_builder_file(self) -> None:
        await self._join_bot(self.anna_id)
        sent = await self._screen("event_participants_xlsx", f"admin:event:xlsx:{self.event_id}")
        document = sent.answer_document.await_args.args[0]
        self.assertEqual([row[0] for row in _sheet_rows(document)[1:]], ["Анна"])
