"""Regression tests for read-only Leaders chat binding validation."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import unittest

from app.handlers.chat_binding import _binding_conflict, _leaders_permission_error


class LeadersChatBindSafetyTests(unittest.TestCase):
    def test_cannot_bind_general_chat_as_leaders_or_reverse(self):
        settings = SimpleNamespace(general_chat_id=-10011, leaders_chat_id=-10022)
        self.assertIsNotNone(_binding_conflict("leaders", -10011, settings))
        self.assertIsNotNone(_binding_conflict("general", -10022, settings))
        self.assertIsNone(_binding_conflict("leaders", -10022, settings))
        self.assertIsNone(_binding_conflict("general", -10011, settings))

    def test_leaders_forum_requires_admin_and_manage_topics(self):
        forum = SimpleNamespace(type="supergroup", is_forum=True)
        ordinary = SimpleNamespace(status="member", can_manage_topics=True)
        no_topics = SimpleNamespace(status="administrator", can_manage_topics=False)
        admin = SimpleNamespace(status="administrator", can_manage_topics=True)
        self.assertIsNotNone(_leaders_permission_error(forum, ordinary))
        self.assertIsNotNone(_leaders_permission_error(forum, no_topics))
        self.assertIsNone(_leaders_permission_error(forum, admin))

    def test_forwarded_binding_checks_before_persisting(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "app" / "handlers" / "admin" / "chat_binding_stability.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_binding_conflict(str(key), chat.id, settings)", source)
        self.assertIn("_leaders_permission_error(actual_chat, member)", source)
        self.assertLess(
            source.index("_leaders_permission_error(actual_chat, member)"),
            source.index("    await _save_binding(", source.index("async def bind_chat_finish_stable")),
        )

    def test_plain_group_supported_and_channel_rejected(self):
        plain = SimpleNamespace(type="supergroup", is_forum=False)
        channel = SimpleNamespace(type="channel", is_forum=False)
        admin = SimpleNamespace(status="administrator", can_manage_topics=False)
        self.assertIsNone(_leaders_permission_error(plain, admin))
        self.assertIsNotNone(_leaders_permission_error(channel, admin))




class LeadersReadOnlyDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = SimpleNamespace(
            admin_ids=[1001], leaders_chat_id=-1001, general_chat_id=-1002,
        )
        self.message = SimpleNamespace(
            from_user=SimpleNamespace(id=1001), answer=AsyncMock(),
        )
        self.session = SimpleNamespace(scalar=AsyncMock(), commit=AsyncMock())
        self.bot = SimpleNamespace(
            id=77,
            get_chat=AsyncMock(return_value=SimpleNamespace(
                type="supergroup", is_forum=True,
            )),
            get_chat_member=AsyncMock(return_value=SimpleNamespace(
                status="administrator", can_manage_topics=True,
            )),
        )

    async def test_only_admin_can_read_diagnostics(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.message.from_user.id = 999
        await leaders_readonly_diagnostics(
            self.message, None, self.settings, self.session, self.bot,
        )
        self.bot.get_chat.assert_not_awaited()
        self.session.scalar.assert_not_awaited()
        self.assertIn("только администратору", self.message.answer.await_args.args[0])

    async def test_saved_ids_are_not_claimed_to_be_live_and_no_mutations(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.session.scalar.side_effect = [
            SimpleNamespace(value=json.dumps({"thread_id": 31, "message_id": 90})),
            SimpleNamespace(value=json.dumps({"thread_state": "creating"})),
            SimpleNamespace(value=json.dumps({"message_state": "uncertain"})),
        ]
        await leaders_readonly_diagnostics(
            self.message, None, self.settings, self.session, self.bot,
        )
        result = self.message.answer.await_args.args[0]
        self.assertIn("thread_id=31 (из БД, не проверен в Telegram)", result)
        self.assertIn("нужна ручная сверка, не создавать повторно", result)
        self.assertIn("доставка не подтверждена", result)
        self.assertIn("Управление темами: да", result)
        self.assertEqual(self.session.scalar.await_count, 3)
        self.session.commit.assert_not_awaited()

    async def test_diagnostics_do_not_read_general_chat_binding(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.settings.leaders_chat_id = self.settings.general_chat_id
        await leaders_readonly_diagnostics(
            self.message, None, self.settings, self.session, self.bot,
        )
        self.bot.get_chat.assert_not_awaited()
        self.session.scalar.assert_not_awaited()
        self.assertIn("не привязан отдельно", self.message.answer.await_args.args[0])

    async def test_plain_chat_mode_is_distinguished_from_forum_topic(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.bot.get_chat.return_value.is_forum = False
        self.session.scalar.side_effect = [
            SimpleNamespace(value=json.dumps({"mode": "plain"})),
            None,
            None,
        ]
        await leaders_readonly_diagnostics(
            self.message, None, self.settings, self.session, self.bot,
        )
        result = self.message.answer.await_args.args[0]
        self.assertIn("Форум: нет", result)
        self.assertIn("обычная группа, отдельной темы нет", result)
        self.session.commit.assert_not_awaited()

if __name__ == "__main__":
    unittest.main()
