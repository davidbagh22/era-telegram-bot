"""Regression coverage for native admin entry points; no Telegram sends."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers.admin import broadcast_native, media_native
from app.handlers.leader import event_quick_composer
from app.keyboards.admin import admin_home_keyboard


def callback_values(keyboard):
    return [button.callback_data for row in keyboard.inline_keyboard
            for button in row if button.callback_data]


class NativeAdminEntrypointsTests(unittest.TestCase):
    def test_admin_home_exposes_media_broadcast_and_event_photo(self):
        values = callback_values(admin_home_keyboard())
        self.assertIn("admin:media", values)
        self.assertIn("admin:campaign:new", values)
        self.assertIn("leader:event:new", values)

    def test_broadcast_audience_is_explicit_and_has_cancel(self):
        values = callback_values(broadcast_native.choose_keyboard())
        self.assertIn("admin:campaign:audience:all", values)
        self.assertIn("admin:campaign:audience:leader", values)
        self.assertIn("admin:campaign:compose:cancel", values)
        self.assertNotIn("admin:campaign:confirm:", values)

    def test_broadcast_permission_requires_matching_active_admin(self):
        settings = SimpleNamespace()
        user = SimpleNamespace(telegram_id=321, is_blocked=False, is_archived=False)
        with patch.object(broadcast_native, "is_full_admin", return_value=True):
            self.assertTrue(broadcast_native.allowed(user, settings, 321))
            self.assertFalse(broadcast_native.allowed(user, settings, 999))
            user.is_blocked = True
            self.assertFalse(broadcast_native.allowed(user, settings, 321))
            user.is_blocked = False
            user.is_archived = True
            self.assertFalse(broadcast_native.allowed(user, settings, 321))
        self.assertFalse(broadcast_native.allowed(None, settings, 321))

    def test_quick_poster_composer_admin_only_override(self):
        settings = SimpleNamespace(feature_native_event_composer="OFF",
                                   native_event_composer_tester_ids=[])
        user = SimpleNamespace(telegram_id=321)
        with patch.object(event_quick_composer, "is_full_admin", return_value=True):
            self.assertTrue(event_quick_composer.enabled_for_user(settings, user))
        with patch.object(event_quick_composer, "is_full_admin", return_value=False):
            self.assertFalse(event_quick_composer.enabled_for_user(settings, user))


class MediaNativeAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_media_privilege_never_reads_scoped_queue(self):
        message = SimpleNamespace(answer=AsyncMock())
        session = SimpleNamespace(execute=AsyncMock(), scalars=AsyncMock())
        with patch.object(media_native, "media_access_level", new=AsyncMock(return_value="no_access")):
            await media_native.show_media(message, object(), SimpleNamespace(media_chat_id=1), session)
        session.execute.assert_not_awaited()
        session.scalars.assert_not_awaited()
        message.answer.assert_awaited_once()
