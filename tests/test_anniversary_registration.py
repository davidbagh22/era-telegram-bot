import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AppSetting
from app.handlers import anniversary as handler
from app.services import anniversary_registration_service as service


class AnniversaryTests(unittest.IsolatedAsyncioTestCase):
    def test_fields_and_deadline(self):
        self.assertEqual(service.clean_field("  Անի   Մարիա ", name=True), "Անի Մարիա")
        self.assertEqual(service.clean_field("Без организации"), "Без организации")
        for value in (None, "", "\nИмя", "123", "/start", "а" * 81):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    service.clean_field(value, name=True)
        self.assertTrue(service.registration_open(datetime(2026, 12, 12, 17, 29, tzinfo=service.START.tzinfo)))
        self.assertFalse(service.registration_open(service.START))
        self.assertEqual(handler.csv_cell(" =1+1"), "' =1+1")

    async def test_registration_is_durable_unique_and_does_not_create_members(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        original = dict(first_name="Анна", last_name="Иванова", organization="Без организации")
        try:
            with patch.object(service, "registration_open", return_value=True):
                async with factory() as session:
                    result = await service.register(session, 123456, original)
                    self.assertEqual(result["telegram_id"], 123456)
                async with factory() as session:
                    result = await service.register(session, 123456, {**original, "first_name": "Другое"})
                    self.assertEqual(result["first_name"], "Анна")
                    self.assertEqual(await session.scalar(select(func.count()).select_from(AppSetting)), 1)
                    from app.database.models import User
                    self.assertEqual(await session.scalar(select(func.count()).select_from(User)), 0)
            async with factory() as session:
                with patch.object(service, "registration_open", return_value=False):
                    with self.assertRaises(ValueError):
                        await service.register(session, 999, original)
                self.assertIsNone(await service.get_registration(session, 999))
        finally:
            await engine.dispose()

    async def test_guest_entry_does_not_require_membership(self):
        message = SimpleNamespace(from_user=SimpleNamespace(id=123), answer=AsyncMock())
        state = AsyncMock()
        with patch.object(service, "get_registration", AsyncMock(return_value=None)), patch.object(service, "registration_open", return_value=True):
            await handler.entry(message, state, object(), None)
        state.clear.assert_awaited_once()
        self.assertEqual(message.answer.call_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data, "anniversary:begin")

    async def test_export_denies_participant_without_querying_database(self):
        message = SimpleNamespace(from_user=SimpleNamespace(id=123), answer=AsyncMock(), answer_document=AsyncMock())
        session = AsyncMock()
        with patch.object(handler, "is_full_admin", return_value=False):
            await handler.export_guests(message, session, None, object())
        session.scalars.assert_not_awaited()
        message.answer_document.assert_not_awaited()

    async def test_save_uses_telegram_sender_and_clears_only_after_commit(self):
        call = SimpleNamespace(from_user=SimpleNamespace(id=123), answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()))
        state = AsyncMock()
        data = dict(first_name="Анна", last_name="Иванова", organization="ЭРА", telegram_id=999)
        state.get_data.return_value = data
        with patch.object(service, "register", AsyncMock(return_value=data)) as register:
            await handler.save(call, state, object(), None)
            self.assertEqual(register.call_args.args[1], 123)
        state.clear.assert_awaited_once()
        self.assertIsNone(call.message.answer.call_args.kwargs["parse_mode"])

    async def test_blocked_user_cannot_register(self):
        call = SimpleNamespace(from_user=SimpleNamespace(id=123), answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()))
        with patch.object(service, "register", AsyncMock()) as register:
            await handler.save(call, AsyncMock(), object(), SimpleNamespace(is_blocked=True, is_archived=False))
        register.assert_not_awaited()

    async def test_dispatcher_routes_guest_deeplink_and_three_fields(self):
        import copy
        from aiogram import Bot, Dispatcher
        from aiogram.types import Update
        dp = Dispatcher()
        dp.include_router(copy.deepcopy(handler.router))
        bot = Bot("0000000000:LOCALTEST")
        bot.session = AsyncMock()
        sender = {"id": 123, "is_bot": False, "first_name": "Guest"}
        chat = {"id": 123, "type": "private"}
        async def send(text, number):
            update = Update.model_validate({"update_id": number, "message": {
                "message_id": number, "date": 1, "chat": chat, "from": sender,
                "text": text, "entities": [{"type": "bot_command", "offset": 0, "length": 6}] if text.startswith("/start") else [],
            }})
            return await dp.feed_update(bot, update, session=object(), user=None)
        with patch.object(service, "get_registration", AsyncMock(return_value=None)), patch.object(service, "registration_open", return_value=True):
            await send("/start anniversary2026", 1)
            method = bot.session.call_args.args[1]
            self.assertEqual(method.reply_markup.inline_keyboard[0][0].callback_data, "anniversary:begin")
            callback = Update.model_validate({"update_id": 2, "callback_query": {
                "id": "abc", "chat_instance": "local", "from": sender, "data": "anniversary:begin",
                "message": {"message_id": 1, "date": 1, "chat": chat, "text": "Invite"},
            }})
            await dp.feed_update(bot, callback, session=object(), user=None)
            await send("Анна", 3)
            await send("Иванова", 4)
            await send("Без организации", 5)
        context = dp.fsm.get_context(bot=bot, chat_id=123, user_id=123)
        self.assertEqual(await context.get_state(), handler.AnniversaryStates.confirm.state)
        self.assertEqual(await context.get_data(), dict(first_name="Анна", last_name="Иванова", organization="Без организации"))
        self.assertEqual(bot.session.call_args.args[1].reply_markup.inline_keyboard[0][0].callback_data, "anniversary:save")
        await dp.storage.close()
