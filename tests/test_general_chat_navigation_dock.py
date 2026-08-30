from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

from aiogram.types import (
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    ReplyKeyboardMarkup,
)

from app.config import Settings
from app.handlers import chat, chat_faq
from app.keyboards.faq import (
    GENERAL_CHAT_EVENTS_TEXT,
    GENERAL_CHAT_PROFILE_TEXT,
    faq_keyboard,
    general_chat_navigation_keyboard,
)
from app.utils.constants import ApplicationStatus
from app.webapp import ADMIN_COMMANDS, USER_COMMANDS, _configure_command_scopes


def _approved_user(telegram_id: int = 777) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        telegram_id=telegram_id,
        application_status=ApplicationStatus.APPROVED,
        role="participant",
        is_blocked=False,
        is_archived=False,
        permission_grants=[],
    )


class GeneralChatKeyboardShapeTests(unittest.TestCase):
    def test_pinned_faq_has_seven_private_deep_links(self) -> None:
        markup = faq_keyboard("era_bot")
        buttons = [button for row in markup.inline_keyboard for button in row]
        self.assertEqual(len(buttons), 7)
        self.assertEqual(buttons[0].text, "📅 Ближайшие события")
        self.assertEqual(buttons[-1].text, "💬 Связаться с командой")
        self.assertTrue(all(button.url and button.url.startswith("https://t.me/era_bot?start=faq_") for button in buttons))
        self.assertTrue(all(button.callback_data is None for button in buttons))

    def test_persistent_group_keyboard_has_only_two_requested_actions(self) -> None:
        markup = general_chat_navigation_keyboard()
        self.assertIsInstance(markup, ReplyKeyboardMarkup)
        self.assertTrue(markup.is_persistent)
        self.assertEqual(len(markup.keyboard), 1)
        self.assertEqual(
            [button.text for button in markup.keyboard[0]],
            [GENERAL_CHAT_EVENTS_TEXT, GENERAL_CHAT_PROFILE_TEXT],
        )


class PinnedFaqRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_events_callback_sends_exact_webapp_route_to_private_chat(self) -> None:
        call = SimpleNamespace(answer=AsyncMock())
        settings = Settings(
            bot_token="1234567890:test-token",
            miniapp_auth_secret="secret",
            miniapp_url="https://era.example/app/",
        )
        user = _approved_user()
        with patch.object(chat_faq, "safe_send", AsyncMock(return_value=True)) as safe_send:
            await chat_faq.faq_events(call, user, SimpleNamespace(id=1), settings)
        args, kwargs = safe_send.call_args
        self.assertEqual(args[1], user.telegram_id)
        button = kwargs["reply_markup"].inline_keyboard[0][0]
        parsed = urlsplit(button.web_app.url)
        self.assertEqual(parse_qs(parsed.query).get("eraPath"), ["events"])

    async def test_profile_callback_sends_exact_webapp_route_to_private_chat(self) -> None:
        call = SimpleNamespace(answer=AsyncMock())
        settings = Settings(
            bot_token="1234567890:test-token",
            miniapp_auth_secret="secret",
            miniapp_url="https://era.example/app/",
        )
        user = _approved_user()
        with patch.object(chat_faq, "safe_send", AsyncMock(return_value=True)) as safe_send:
            await chat_faq.faq_profile(call, user, SimpleNamespace(id=1), settings)
        _, kwargs = safe_send.call_args
        button = kwargs["reply_markup"].inline_keyboard[0][0]
        parsed = urlsplit(button.web_app.url)
        self.assertEqual(parse_qs(parsed.query).get("eraPath"), ["profile"])


class GeneralChatReplyRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_bottom_events_press_is_deleted_from_group_and_routed_privately(self) -> None:
        settings = Settings(
            bot_token="1234567890:test-token",
            general_chat_id=-100555,
            miniapp_auth_secret="secret",
            miniapp_url="https://era.example/app/",
        )
        message = SimpleNamespace(
            text=GENERAL_CHAT_EVENTS_TEXT,
            chat=SimpleNamespace(id=-100555, type="supergroup"),
            from_user=SimpleNamespace(id=777),
            delete=AsyncMock(),
        )
        user = _approved_user()
        with patch.object(chat, "safe_send", AsyncMock(return_value=True)) as safe_send:
            await chat.general_chat_quick_navigation(message, SimpleNamespace(), user, settings)
        message.delete.assert_awaited_once()
        _, kwargs = safe_send.call_args
        button = kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(parse_qs(urlsplit(button.web_app.url).query).get("eraPath"), ["events"])


class CommandScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_slash_commands_are_explicitly_hidden(self) -> None:
        bot = SimpleNamespace(set_my_commands=AsyncMock())
        settings = SimpleNamespace(
            general_chat_id=-1001,
            internal_department_chat_id=-1002,
            external_department_chat_id=-1003,
            leaders_chat_id=-1004,
            admin_ids=[999],
        )
        await _configure_command_scopes(bot, settings)
        calls = bot.set_my_commands.await_args_list

        self.assertEqual(calls[0].args[0], [])
        self.assertEqual(calls[1].args[0], USER_COMMANDS)
        self.assertIsInstance(calls[1].kwargs["scope"], BotCommandScopeAllPrivateChats)
        self.assertEqual(calls[2].args[0], [])
        self.assertIsInstance(calls[2].kwargs["scope"], BotCommandScopeAllGroupChats)

        group_chat_scopes = [
            call.kwargs["scope"].chat_id
            for call in calls[3:7]
            if isinstance(call.kwargs.get("scope"), BotCommandScopeChat)
        ]
        self.assertEqual(set(group_chat_scopes), {-1001, -1002, -1003, -1004})
        self.assertEqual(calls[-1].args[0], ADMIN_COMMANDS)
        self.assertEqual(calls[-1].kwargs["scope"].chat_id, 999)


if __name__ == "__main__":
    unittest.main()
