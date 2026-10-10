from datetime import datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.content.literature_issues import ISSUES, get_issue, render_issue, validate_issue
from app.database.base import Base
from app.database.models import AppSetting, User
from app.handlers.book_club import change_subscription, navigate
from app.services.book_club_service import daily_job, mark_progress, progress, start
from app.utils.constants import ApplicationStatus


def test_all_48_complete_distinct_and_telegram_sized():
    assert len(ISSUES) == 48
    for i, issue in enumerate(ISSUES, 1):
        validate_issue(issue)
        assert issue.number == i
        assert len(render_issue(i)) < 4096
    for field in ('title', 'summary', 'example', 'critical_view', 'reflection_question', 'practical_task'):
        assert len({getattr(issue, field) for issue in ISSUES}) == 48
    assert get_issue(24).title == 'Играй роль идеального придворного'
    assert get_issue(35).title == 'Овладей искусством выбирать момент'
    assert get_issue(48).title == 'Будь бесформенным'


class LiteratureTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token='1234567890:test-token', general_chat_id=-100123)
        self.bot = SimpleNamespace(send_message=AsyncMock())
        async with self.sessions() as s:
            s.add_all([User(id=i, telegram_id=100+i, first_name='Test', book_club_subscribed=i != 4,
                           application_status=ApplicationStatus.PENDING if i == 5 else ApplicationStatus.APPROVED,
                           is_archived=i == 2, is_blocked=i == 3) for i in range(1, 6)])
            await s.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    def callback(self, data):
        return SimpleNamespace(data=data, answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()))

    async def send_today(self):
        with patch('app.services.book_club_service.datetime') as clock, patch('app.services.notification_service._session_factory', return_value=self.sessions):
            clock.now.return_value = datetime(2026, 10, 10, 19, tzinfo=ZoneInfo('Asia/Yerevan'))
            await daily_job(self.bot, self.settings, self.sessions)

    async def test_delivery_only_eligible_opted_in_no_group_and_no_duplicates(self):
        await self.send_today()
        await self.send_today()
        self.bot.send_message.assert_awaited_once()
        args, kwargs = self.bot.send_message.call_args
        assert args[0] == 101
        assert 'Выпуск 1/48' in args[1]
        assert kwargs['parse_mode'] == 'HTML'

    async def test_subscription_repeat_and_progress_survive_optout(self):
        async with self.sessions() as s:
            user = await s.get(User, 1)
            await mark_progress(s, user, 1, 'read')
            await mark_progress(s, user, 1, 'read')
            await mark_progress(s, user, 2, 'task')
            await change_subscription(self.callback('bookclub:unsubscribe'), user, s)
            await change_subscription(self.callback('bookclub:unsubscribe'), user, s)
        await self.send_today()
        self.bot.send_message.assert_not_awaited()
        async with self.sessions() as s:
            user = await s.get(User, 1)
            assert not user.book_club_subscribed
            assert await progress(s, user) == {'read': 1, 'task': 1}
            other = await s.get(User, 4)
            assert await progress(s, other) == {'read': 0, 'task': 0}
            await change_subscription(self.callback('bookclub:subscribe'), user, s)
            await change_subscription(self.callback('bookclub:subscribe'), user, s)
        await self.send_today()
        self.bot.send_message.assert_awaited_once()

    async def test_archived_user_cannot_subscribe_but_can_opt_out(self):
        async with self.sessions() as s:
            user = await s.get(User, 2)
            user.book_club_subscribed = False
            await s.commit()
            call = self.callback('bookclub:subscribe')
            await change_subscription(call, user, s)
            assert call.answer.call_args.kwargs['show_alert']
            assert not user.book_club_subscribed

    async def test_bad_callback_rejected_without_progress_write(self):
        async with self.sessions() as s:
            user = await s.get(User, 1)
            for data in ['bookclub:read:49', 'bookclub:task:-1', 'bookclub:list:7', 'bookclub:issue:no', 'bookclub:issue']:
                call = self.callback(data)
                await navigate(call, user, s)
                assert call.answer.call_args.kwargs['show_alert']
            assert await progress(s, user) == {'read': 0, 'task': 0}

    async def test_start_idempotent_and_completed_program_silent(self):
        async with self.sessions() as s:
            first = await start(s)
            assert first == await start(s)
            await s.commit()
            rows = (await s.scalars(select(AppSetting).where(AppSetting.key == 'book_club_start_date'))).all()
            assert len(rows) == 1
        with patch('app.services.book_club_service.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 27, 19, tzinfo=ZoneInfo('Asia/Yerevan'))
            await daily_job(self.bot, self.settings, self.sessions)
        self.bot.send_message.assert_not_awaited()

class ReflectionTests(LiteratureTests):
    async def test_private_answers_update_and_do_not_mix_users(self):
        from app.services.book_club_service import save_reflection, reflection_summary
        from app.handlers.book_club import my_reflections
        async with self.sessions() as session:
            user = await session.get(User, 1)
            other = await session.get(User, 4)
            await save_reflection(session, user, 1, 'First thought')
            await save_reflection(session, user, 1, 'Changed thought')
            await save_reflection(session, other, 1, 'Other participant')
            assert await reflection_summary(session, user) == [(1, 'Changed thought')]
            call = self.callback('bookclub:delete_confirm')
            await my_reflections(call, user, session, SimpleNamespace(clear=AsyncMock()))
            assert await reflection_summary(session, user) == []
            assert await reflection_summary(session, other) == [(1, 'Other participant')]
