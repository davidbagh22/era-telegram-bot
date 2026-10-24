"""Regression tests for read-only Leaders chat binding validation."""
from pathlib import Path
from types import SimpleNamespace
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


if __name__ == "__main__":
    unittest.main()
