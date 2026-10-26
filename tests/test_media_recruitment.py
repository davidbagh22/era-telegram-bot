from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import media_recruitment_service as service
from app.services.notification_service import NotificationDeliveryResult


class MediaRecruitmentTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.settings = SimpleNamespace(general_chat_id=-1001, media_chat_id=-1002, leaders_chat_id=-1003, era_chair_user_id=10, feature_media="ALL")
        self.bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="ERA_1bot")))
        self.session = AsyncMock()
        self.session.scalar.return_value = SimpleNamespace(leader_id=None)
        self.factory = MagicMock()
        self.factory.return_value.__aenter__ = AsyncMock(return_value=self.session)
        self.factory.return_value.__aexit__ = AsyncMock(return_value=False)

    async def test_notice_uses_shared_durable_topic_delivery_and_exact_buttons(self):
        with patch.object(service, "media_config", AsyncMock(return_value={"join_enabled": True})), patch.object(service, "send_general_topic_once", AsyncMock(return_value=NotificationDeliveryResult(True, "sent", False, 1, message_id=42))) as send:
            self.assertEqual(await service.publish_media_recruitment(self.bot, self.settings, self.factory), "sent")
            self.assertEqual(send.call_args.args[2], "notifications")
            self.assertEqual(send.call_args.kwargs["delivery_key"], service.CAMPAIGN_KEY)
            buttons = send.call_args.kwargs["reply_markup"].inline_keyboard
            self.assertEqual(buttons[0][0].url, "https://t.me/ERA_1bot?start=media_join")
            self.assertEqual(buttons[1][0].url, "https://t.me/davidbs2")

    async def test_occupied_role_and_disabled_invitation_are_not_advertised(self):
        with patch.object(service, "media_config", AsyncMock(return_value={"join_enabled": True})), patch.object(service, "send_general_topic_once", AsyncMock()) as send:
            self.session.scalar.return_value = SimpleNamespace(leader_id=20)
            self.assertEqual(await service.publish_media_recruitment(self.bot, self.settings, self.factory), "leader_already_assigned")
            send.assert_not_awaited()
        with patch.object(service, "media_config", AsyncMock(return_value={"join_enabled": False})), patch.object(service, "send_general_topic_once", AsyncMock()) as send:
            self.assertEqual(await service.publish_media_recruitment(self.bot, self.settings, self.factory), "invitation_unavailable")
            send.assert_not_awaited()

    async def test_wrong_bot_and_cross_chat_binding_block_send(self):
        with patch.object(service, "send_general_topic_once", AsyncMock()) as send:
            self.settings.media_chat_id = self.settings.general_chat_id
            self.assertEqual(await service.publish_media_recruitment(self.bot, self.settings, self.factory), "not_configured")
            self.settings.media_chat_id = -1002
            self.bot.get_me.return_value = SimpleNamespace(username="other_bot")
            self.assertEqual(await service.publish_media_recruitment(self.bot, self.settings, self.factory), "wrong_bot")
            send.assert_not_awaited()

    async def test_uncertain_delivery_keeps_the_same_key_for_recovery(self):
        with patch.object(service, "media_config", AsyncMock(return_value={"join_enabled": True})), patch.object(service, "send_general_topic_once", AsyncMock(return_value=NotificationDeliveryResult(False, "uncertain", True, 1))) as send:
            for _ in range(2):
                self.assertEqual(await service.publish_media_recruitment(self.bot, self.settings, self.factory), "uncertain")
            self.assertEqual({c.kwargs["delivery_key"] for c in send.call_args_list}, {service.CAMPAIGN_KEY})
