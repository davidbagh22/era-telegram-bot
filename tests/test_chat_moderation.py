import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiogram.dispatcher.event.bases import SkipHandler

from app.handlers import chat
from app.utils.constants import ApplicationStatus, Role


def make_user(role=Role.PARTICIPANT, status=ApplicationStatus.APPROVED, blocked=False, archived=False):
    return SimpleNamespace(
        id=1,
        role=role,
        application_status=status,
        is_blocked=blocked,
        is_archived=archived,
        permission_grants=[],
    )


class FakeMessage:
    def __init__(self, chat_id=100, user_id=200, text="hello"):
        self.chat = SimpleNamespace(id=chat_id, type="supergroup")
        self.from_user = SimpleNamespace(id=user_id)
        self.text = text
        self.date = None
        self.deleted = False
        self.replies: list[str] = []

    async def delete(self):
        self.deleted = True

    async def reply(self, text, **kwargs):
        self.replies.append(text)


class FakeBot:
    def __init__(self, admin_ids: set[int] | None = None):
        self.admin_ids = admin_ids or set()
        self.sent_dms: list[tuple[int, str]] = []

    async def get_chat_member(self, chat_id, user_id):
        status = "administrator" if user_id in self.admin_ids else "member"
        return SimpleNamespace(status=status)

    async def send_message(self, chat_id, text, **kwargs):
        self.sent_dms.append((chat_id, text))


class FakeSession:
    def __init__(self, setting=None):
        self.setting = setting

    async def scalar(self, *args, **kwargs):
        return self.setting


def moderation_setting(enabled: bool):
    return SimpleNamespace(is_enabled=enabled)


class ChatModerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_moderation_skips(self):
        message = FakeMessage()
        session = FakeSession(setting=moderation_setting(False))
        with self.assertRaises(SkipHandler):
            await chat.moderation_gate(message, FakeBot(), None, session)
        self.assertFalse(message.deleted)

    async def test_approved_member_skips(self):
        message = FakeMessage()
        session = FakeSession(setting=moderation_setting(True))
        with self.assertRaises(SkipHandler):
            await chat.moderation_gate(message, FakeBot(), make_user(), session)
        self.assertFalse(message.deleted)

    async def test_privileged_role_skips(self):
        message = FakeMessage()
        session = FakeSession(setting=moderation_setting(True))
        leader = make_user(role=Role.LEADER, status=ApplicationStatus.PENDING)
        with self.assertRaises(SkipHandler):
            await chat.moderation_gate(message, FakeBot(), leader, session)
        self.assertFalse(message.deleted)

    async def test_real_chat_admin_skips(self):
        message = FakeMessage(user_id=555)
        session = FakeSession(setting=moderation_setting(True))
        bot = FakeBot(admin_ids={555})
        with self.assertRaises(SkipHandler):
            await chat.moderation_gate(message, bot, None, session)
        self.assertFalse(message.deleted)

    async def test_unapproved_user_deleted_and_notified(self):
        chat._dm_notice_sent.clear()
        message = FakeMessage(user_id=777)
        session = FakeSession(setting=moderation_setting(True))
        bot = FakeBot()
        await chat.moderation_gate(message, bot, None, session)
        self.assertTrue(message.deleted)
        self.assertEqual(len(bot.sent_dms), 1)
        self.assertIn("регистрац", bot.sent_dms[0][1].lower())

    async def test_notice_rate_limit(self):
        chat._dm_notice_sent.clear()
        session = FakeSession(setting=moderation_setting(True))
        bot = FakeBot()
        first = FakeMessage(user_id=999)
        await chat.moderation_gate(first, bot, None, session)
        second = FakeMessage(user_id=999)
        await chat.moderation_gate(second, bot, None, session)
        self.assertTrue(first.deleted)
        self.assertTrue(second.deleted)
        self.assertEqual(len(bot.sent_dms), 1)

    async def test_moderation_on_requires_privileged_role(self):
        message = FakeMessage()
        session = FakeSession()
        await chat.moderation_on(message, make_user(role=Role.PARTICIPANT), session)
        self.assertIn("только руководитель", message.replies[0])

    async def test_moderation_on_for_admin(self):
        message = FakeMessage()
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        session.add = Mock()
        await chat.moderation_on(message, make_user(role=Role.ADMIN), session)
        self.assertTrue(session.add.called)
        added = session.add.call_args[0][0]
        self.assertTrue(added.is_enabled)
        self.assertEqual(added.chat_id, message.chat.id)


if __name__ == "__main__":
    unittest.main()
