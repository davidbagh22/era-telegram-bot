import copy
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram import Bot, Dispatcher
from aiogram.types import Update

from app.handlers import event_registration_link as link_handler
from app.handlers.leader import event_quick_composer as composer
from app.handlers.admin.events_block6 import public_event_keyboard
from app.handlers.participant import events_stability_block8 as events
from app.utils.constants import EventStatus
from app.utils.deep_links import (
    parse_event_registration_payload,
    telegram_event_registration_url,
)


class EventDirectRegistrationTests(unittest.IsolatedAsyncioTestCase):
    def test_link_payload_is_bounded_and_does_not_accept_other_routes(self):
        self.assertEqual(
            telegram_event_registration_url("@ERA_1bot", 42),
            "https://t.me/ERA_1bot?start=event_42",
        )
        self.assertEqual(parse_event_registration_payload("event_42"), 42)
        for bad in (None, "", "event_0", "event_-1", "event_2147483648",
                    "event_1evil", "event_١", "event_1/other", "anniversary2026"):
            with self.subTest(bad=bad):
                self.assertIsNone(parse_event_registration_payload(bad))
        self.assertEqual(telegram_event_registration_url("@ERA_1bot", -1), "")

    async def test_deeplink_is_dispatched_to_exact_event_card_without_registering(self):
        dp = Dispatcher()
        dp.include_router(copy.deepcopy(link_handler.router))
        bot = Bot("0000000000:LOCALTEST")
        bot.session = AsyncMock()
        message = {
            "update_id": 1, "message": {
                "message_id": 1, "date": 1,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 123, "is_bot": False, "first_name": "Guest"},
                "text": "/start event_42",
                "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
            },
        }
        with patch.object(link_handler, "show_public_event_registration_card", new_callable=AsyncMock) as show:
            await dp.feed_update(
                bot, Update.model_validate(message), user=None,
                session=object(), settings=SimpleNamespace(),
            )
        show.assert_awaited_once()
        self.assertEqual(show.call_args.args[3], 42)
        self.assertEqual(show.call_args.kwargs["telegram_id"], 123)
        await dp.storage.close()

    async def test_no_guest_bypass_or_draft_leak(self):
        message = SimpleNamespace(answer=AsyncMock())
        session = AsyncMock()
        await events.show_public_event_registration_card(message, None, session, 42)
        session.get.assert_not_awaited()
        message.answer.assert_awaited_once()

        approved = SimpleNamespace(application_status="approved",
                                   is_blocked=False, is_archived=False, id=2)
        session.get.return_value = SimpleNamespace(id=42, status=EventStatus.DRAFT)
        message.answer.reset_mock()
        await events.show_public_event_registration_card(message, approved, session, 42)
        message.answer.assert_awaited_once()
        self.assertIn("недоступно", message.answer.call_args.args[0])

    async def test_approved_user_receives_same_registration_button_as_afisha(self):
        user = SimpleNamespace(application_status="approved",
                               is_blocked=False, is_archived=False, id=2)
        message = SimpleNamespace(answer=AsyncMock())
        session = AsyncMock()
        event = SimpleNamespace(id=42, status=EventStatus.REGISTRATION_OPEN,
                                participant_limit=None)
        session.get.side_effect = [event, None]
        session.scalar.return_value = 0
        with (
            patch.object(events, "registration_stats", new_callable=AsyncMock,
                         return_value={"free": 50, "registered": 0}),
            patch.object(events, "registration_is_closed", return_value=False),
            patch.object(events, "send_event_card", new_callable=AsyncMock) as send,
        ):
            await events.show_public_event_registration_card(
                message, user, session, 42,
            )
        send.assert_awaited_once()
        keyboard = send.call_args.kwargs["keyboard"]
        self.assertEqual(keyboard.inline_keyboard[0][0].callback_data, "event:join:42")

    async def test_published_chat_button_uses_bot_registration_link(self):
        event = SimpleNamespace(id=42)
        bot = SimpleNamespace()
        settings = SimpleNamespace(bot_username="ERA_1bot")
        keyboard = await public_event_keyboard(bot, settings, event)
        self.assertEqual(
            keyboard.inline_keyboard[0][0].url,
            "https://t.me/ERA_1bot?start=event_42",
        )

    def test_photo_editor_available_for_active_full_admin_when_flag_off(self):
        settings = SimpleNamespace(feature_native_event_composer="OFF", admin_ids=[123],
                                   native_event_composer_tester_ids=[])
        admin = SimpleNamespace(telegram_id=123, is_blocked=False, is_archived=False,
                                role="participant", permission_grants=[])
        self.assertTrue(composer.can_use_quick_composer(settings, admin, 123))
        self.assertFalse(composer.can_use_quick_composer(settings, admin, 999))
        admin.is_blocked = True
        self.assertFalse(composer.can_use_quick_composer(settings, admin, 123))

    async def test_editor_has_explicit_photo_attachment_button(self):
        form = {"title": "Конференция", "description": "Программа"}
        state = AsyncMock()
        state.get_data.return_value = {"quick_form": form, "quick_token": "0123456789abcdef"}
        message = SimpleNamespace(
            chat=SimpleNamespace(id=123), bot=AsyncMock(),
            answer=AsyncMock(return_value=SimpleNamespace(message_id=77)),
        )
        await composer.show_card(message, state)
        buttons = [button for row in message.answer.call_args.kwargs["reply_markup"].inline_keyboard for button in row]
        self.assertTrue(any("фото" in b.text.lower() and "leader:eventq:photo:" in b.callback_data
                            for b in buttons))
