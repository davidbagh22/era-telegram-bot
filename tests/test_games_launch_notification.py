"""Game launch announcement must be gated, topic-specific and idempotent."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from unittest import IsolatedAsyncioTestCase

from app.services.games_launch_service import publish_games_launch


class GameLaunchTests(IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch("app.services.games_launch_service.refresh_games_pin", new=AsyncMock(return_value=True))
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_games_off_never_posts_or_creates_topic(self):
        settings = SimpleNamespace(feature_games="OFF", general_chat_id=-100123456)
        with patch("app.services.games_launch_service.ensure_topic", new_callable=AsyncMock) as topic, patch(
            "app.services.games_launch_service.send_general_topic", new_callable=AsyncMock
        ) as send:
            await publish_games_launch(object(), settings, object())
        topic.assert_not_awaited()
        send.assert_not_awaited()


    async def test_games_testers_mode_never_announces_public_launch(self):
        settings = SimpleNamespace(feature_games="TESTERS", general_chat_id=-100123456)
        with patch("app.services.games_launch_service.ensure_topic", new_callable=AsyncMock) as topic, patch(
            "app.services.games_launch_service.send_general_topic", new_callable=AsyncMock
        ) as send:
            await publish_games_launch(object(), settings, object())
        topic.assert_not_awaited()
        send.assert_not_awaited()


    async def test_games_announcement_uses_notifications_topic_and_stable_delivery_key(self):
        settings = SimpleNamespace(feature_games="ALL", general_chat_id=-100123456)
        with patch("app.services.games_launch_service.ensure_topic", new=AsyncMock(return_value=99)), patch(
            "app.services.games_launch_service.send_general_topic", new=AsyncMock(return_value=True)
        ) as send:
            await publish_games_launch(object(), settings, object())
        assert send.await_count == 1
        args, kwargs = send.await_args
        assert args[2] == "notifications"
        assert kwargs["delivery_key"] == "games-notification-v1"
        assert kwargs["reply_markup"].inline_keyboard[0][0].url == "https://t.me/c/123456/99"
        announcement = args[3]
        for format_name in (
            "быстрый и командный квиз", "Правда или миф", "угадай страну", "хронология",
            "словесная цепочка", "ассоциации", "логика", "культурный блиц", "память",
            "командная дуэль",
        ):
            assert format_name in announcement
