from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.config import Settings
from app.database.models import User
from app.handlers.chat_binding import CHAT_KEYS as BIND_CHAT_KEYS
from app.services.chat_access_service import check_chat_access, chat_key_for_id
from app.services.chat_registry_service import check_chats_health
from app.utils.constants import ApplicationStatus


class MediaChatRegistryTests(unittest.IsolatedAsyncioTestCase):
    def _settings(self, **overrides) -> Settings:
        values = {
            "bot_token": "1234567890:test-token",
            "general_chat_id": None,
            "internal_department_chat_id": None,
            "external_department_chat_id": None,
            "leaders_chat_id": None,
            "media_chat_id": None,
            "era_channel_id": "",
        }
        values.update(overrides)
        return Settings(**values)

    def test_bind_media_is_registered(self) -> None:
        self.assertIn("media", BIND_CHAT_KEYS)
        self.assertEqual(BIND_CHAT_KEYS["media"][0], "media_chat_id")

    def test_approved_participant_without_media_membership_is_denied(self) -> None:
        user = User(
            telegram_id=1,
            first_name="Participant",
            application_status=ApplicationStatus.APPROVED,
        )
        decision = check_chat_access(user, "media")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "media_approval_required")

    def test_approved_media_member_can_access_media(self) -> None:
        direction = SimpleNamespace(name="Медиа", leader_id=None)
        membership = SimpleNamespace(direction=direction, status="approved")
        user = SimpleNamespace(
            application_status=ApplicationStatus.APPROVED,
            is_blocked=False,
            is_archived=False,
            role="participant",
            directions=[membership],
        )
        decision = check_chat_access(user, "media")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "approved")

    def test_unapproved_participant_cannot_access_media(self) -> None:
        user = User(
            telegram_id=1,
            first_name="Participant",
            application_status=ApplicationStatus.PENDING,
        )
        decision = check_chat_access(user, "media")
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.pending)

    def test_media_chat_id_is_resolved(self) -> None:
        settings = self._settings(media_chat_id=-1001234567890)
        self.assertEqual(chat_key_for_id(settings, -1001234567890), "media")
        self.assertIn(-1001234567890, settings.chat_ids)

    async def test_channel_health_requires_post_permission_without_test_post(self) -> None:
        settings = self._settings(era_channel_id=-100999)
        bot = SimpleNamespace(
            id=42,
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(
                    status="administrator",
                    can_post_messages=False,
                    can_edit_messages=False,
                )
            ),
            send_message=AsyncMock(),
        )
        results = await check_chats_health(bot, settings)
        channel = next(item for item in results if item.chat_key == "era_channel")
        self.assertFalse(channel.ok)
        self.assertEqual(channel.detail, "cannot_post_messages")
        bot.send_message.assert_not_called()

    async def test_channel_health_accepts_post_permission(self) -> None:
        settings = self._settings(era_channel_id=-100999)
        bot = SimpleNamespace(
            id=42,
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(
                    status="administrator",
                    can_post_messages=True,
                    can_edit_messages=True,
                )
            ),
        )
        results = await check_chats_health(bot, settings)
        channel = next(item for item in results if item.chat_key == "era_channel")
        self.assertTrue(channel.ok)
        self.assertEqual(channel.detail, "ok:post+edit")


if __name__ == "__main__":
    unittest.main()
