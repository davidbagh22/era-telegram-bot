from datetime import date, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.services.literature_channel_announcement import launch_window_open, publish_literature_channel_launch


def test_catchup_is_limited_to_active_program():
    assert not launch_window_open(date(2026, 10, 9))
    assert launch_window_open(date(2026, 10, 10))
    assert launch_window_open(date(2026, 10, 11))
    assert launch_window_open(date(2026, 11, 26))
    assert not launch_window_open(date(2026, 11, 27))


class LaunchCatchupTests(IsolatedAsyncioTestCase):
    async def test_late_deploy_delivers_once_across_scheduler_retries(self):
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            settings = Settings(bot_token='1234567890:test-token', era_channel_id=-100456)
            bot = SimpleNamespace(send_message=AsyncMock())
            with patch('app.services.literature_channel_announcement.datetime') as clock, patch('app.services.notification_service._session_factory', return_value=sessions):
                clock.now.return_value = datetime(2026, 10, 11, 9)
                await publish_literature_channel_launch(bot, settings)
                await publish_literature_channel_launch(bot, settings)
            bot.send_message.assert_awaited_once()
            assert bot.send_message.call_args.args[0] == -100456
            assert 'Первый выпуск уже сегодня' not in bot.send_message.call_args.args[1]
        finally:
            await engine.dispose()
