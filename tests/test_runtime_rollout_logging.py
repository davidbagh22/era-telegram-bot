from unittest import IsolatedAsyncioTestCase

from app.bot import create_bot
from app.config import Settings


class RolloutLoggingTests(IsolatedAsyncioTestCase):
    async def test_rollout_flags_are_observable_without_tokens_or_recipient_ids(self):
        settings = Settings(bot_token='1234567890:private-token', feature_games='ALL',
                            feature_management_reports='ALL', admin_ids=[999999999999])
        with self.assertLogs('app.bot', level='INFO') as capture:
            bot = create_bot(settings)
        await bot.session.close()
        log = '\\n'.join(capture.output)
        assert 'games=ALL reports=ALL' in log
        assert 'reports_at=09:00 Europe/Moscow' in log
        assert settings.bot_token not in log
        assert '999999999999' not in log
