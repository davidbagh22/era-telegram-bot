"""Safe, mocked media recruitment campaign regression coverage."""
import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.media_recruitment_service import (
    MEDIA_JOIN_DM_KEY, MEDIA_JOIN_DM_TEXT, publish_media_join_direct_invitation,
)


class _Factory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        session = self.session

        class Context:
            async def __aenter__(self):
                return session

            async def __aexit__(self, *_):
                return False
        return Context()


class DirectMediaRecruitmentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="ERA_1bot")))
        self.settings = SimpleNamespace(
            media_join_dm_campaign_enabled=False,
            era_chair_user_id=22,
            media_chat_url="https://t.me/+f03ksvhCMKc5NDBi",
        )
        self.session = SimpleNamespace(
            scalar=AsyncMock(return_value=None),
            get=AsyncMock(return_value=SimpleNamespace(
                is_blocked=False, is_archived=False, application_status="approved")),
        )
        self.factory = _Factory(self.session)

    async def test_disabled_is_silent(self):
        with patch("app.services.admin_broadcast_service.send_personal_broadcast",
                   new_callable=AsyncMock) as send:
            self.assertEqual(await publish_media_join_direct_invitation(
                self.bot, self.settings, self.factory), "disabled")
            self.bot.get_me.assert_not_awaited()
            send.assert_not_awaited()

    async def test_mismatched_chat_is_silent(self):
        self.settings.media_join_dm_campaign_enabled = True
        self.settings.media_chat_url = "https://t.me/unexpected"
        with patch("app.services.admin_broadcast_service.send_personal_broadcast",
                   new_callable=AsyncMock) as send:
            self.assertEqual(await publish_media_join_direct_invitation(
                self.bot, self.settings, self.factory), "unexpected_chat")
            send.assert_not_awaited()

    async def test_existing_campaign_never_creates_again(self):
        self.settings.media_join_dm_campaign_enabled = True
        self.session.scalar.return_value = SimpleNamespace(status="sent")
        with patch("app.services.admin_broadcast_service.send_personal_broadcast",
                   new_callable=AsyncMock) as send:
            self.assertEqual(await publish_media_join_direct_invitation(
                self.bot, self.settings, self.factory), "existing:sent")
            send.assert_not_awaited()

    async def test_new_campaign_uses_authorized_stable_key(self):
        self.settings.media_join_dm_campaign_enabled = True
        with patch("app.services.admin_broadcast_service.send_personal_broadcast",
                   new=AsyncMock(return_value=SimpleNamespace(total=4, sent=3, failed=1))) as send:
            self.assertEqual(await publish_media_join_direct_invitation(
                self.bot, self.settings, self.factory), "created")
            self.assertEqual(send.await_count, 1)
            kwargs = send.await_args.kwargs
            self.assertEqual(kwargs["campaign_key"], MEDIA_JOIN_DM_KEY)
            self.assertEqual(kwargs["audience"], "all")
            self.assertEqual(kwargs["author_id"], 22)
            self.assertIn("https://t.me/+f03ksvhCMKc5NDBi", MEDIA_JOIN_DM_TEXT)
            self.assertIn("сертификаты", MEDIA_JOIN_DM_TEXT)
            self.assertEqual(len(hashlib.sha256(f"22:{MEDIA_JOIN_DM_KEY}".encode()).hexdigest()), 64)

    async def test_missing_chair_or_inactive_chair_never_sends(self):
        self.settings.media_join_dm_campaign_enabled = True
        with patch("app.services.admin_broadcast_service.send_personal_broadcast",
                   new_callable=AsyncMock) as send:
            self.settings.era_chair_user_id = None
            self.assertEqual(await publish_media_join_direct_invitation(
                self.bot, self.settings, self.factory), "chair_not_configured")
            self.settings.era_chair_user_id = 22
            self.session.get.return_value = SimpleNamespace(
                is_blocked=True, is_archived=False, application_status="approved")
            self.assertEqual(await publish_media_join_direct_invitation(
                self.bot, self.settings, self.factory), "chair_account_unavailable")
            send.assert_not_awaited()
