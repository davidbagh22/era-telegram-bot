from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import AuditLog, Project, User, UserQuestion
from app.handlers.admin.support_bot import SupportAnswer, support_answer
from app.services.scheduler_service import deliver_support_answers, send_review_sla_reminders
from app.utils.constants import ApplicationStatus, ProjectStatus, Role


class SupportSlaTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token='1234567890:test', feature_review_reminders='TESTERS', review_reminder_recipient_ids=[11])
        self.bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=45)))
        self.now = datetime(2026, 10, 17, 8, tzinfo=timezone.utc)
        self.state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=11, user_id=11))
        self.factory_patch = patch('app.services.notification_service._session_factory', return_value=self.sessions)
        self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)
        self.admin_patch = patch('app.services.scheduler_service.admin_notification_recipients', AsyncMock(return_value={11, 99, -100123}))
        self.admin_patch.start()
        self.addCleanup(self.admin_patch.stop)
        async with self.sessions() as session:
            self.admin = User(telegram_id=11, first_name='Admin', role=Role.ADMIN, application_status=ApplicationStatus.APPROVED)
            self.member = User(telegram_id=22, first_name='Member', application_status=ApplicationStatus.APPROVED)
            session.add_all([self.admin, self.member])
            await session.flush()
            self.question = UserQuestion(user_id=self.member.id, text='Private support text', created_at=self.now-timedelta(hours=25))
            self.project = Project(author_id=self.member.id, title='Private project', short_description='Idea',
                                   status=ProjectStatus.INITIAL_REVIEW, submitted_at=self.now-timedelta(hours=73))
            session.add_all([self.question, self.project])
            await session.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_sla_stages_are_private_once_after_restart_and_stop_after_resolution(self):
        await send_review_sla_reminders(self.bot, self.settings, self.sessions, now=self.now)
        await send_review_sla_reminders(self.bot, self.settings, self.sessions, now=self.now+timedelta(hours=1))
        assert self.bot.send_message.await_count == 2
        assert all(call.args[0] == 11 for call in self.bot.send_message.await_args_list)
        assert all('Private support text' not in str(call) for call in self.bot.send_message.await_args_list)
        await send_review_sla_reminders(self.bot, self.settings, self.sessions, now=self.now+timedelta(hours=74))
        assert self.bot.send_message.await_count == 4
        async with self.sessions() as session:
            (await session.get(Project, self.project.id)).status = ProjectStatus.APPROVED
            (await session.get(UserQuestion, self.question.id)).status = 'answered'
            await session.commit()
        await send_review_sla_reminders(self.bot, self.settings, self.sessions, now=self.now+timedelta(days=10))
        assert self.bot.send_message.await_count == 4

    async def test_reminders_do_not_infer_testers_from_other_features_and_off_sends_nothing(self):
        self.settings.review_reminder_recipient_ids = []
        self.settings.feature_tester_ids = [11]
        await send_review_sla_reminders(self.bot, self.settings, self.sessions, now=self.now)
        self.settings.feature_review_reminders = 'OFF'
        self.settings.review_reminder_recipient_ids = [11]
        await send_review_sla_reminders(self.bot, self.settings, self.sessions, now=self.now)
        self.bot.send_message.assert_not_awaited()

    async def test_backlog_is_bounded_and_later_items_are_not_starved(self):
        async with self.sessions() as session:
            session.add_all([UserQuestion(user_id=self.member.id, text='Private support text',
                created_at=self.now-timedelta(hours=25)) for _ in range(6)])
            await session.commit()
        await send_review_sla_reminders(self.bot, self.settings, self.sessions, now=self.now)
        assert self.bot.send_message.await_count == 6  # one project, five questions
        await send_review_sla_reminders(self.bot, self.settings, self.sessions, now=self.now)
        assert self.bot.send_message.await_count == 8
        await send_review_sla_reminders(self.bot, self.settings, self.sessions, now=self.now)
        assert self.bot.send_message.await_count == 8

    async def test_committed_answer_recovers_and_cannot_send_twice(self):
        async with self.sessions() as session:
            item = await session.get(UserQuestion, self.question.id)
            item.admin_answer, item.answered_by, item.status = 'A saved answer', self.admin.id, 'answer_pending'
            await session.commit()
        await deliver_support_answers(self.bot, self.settings, self.sessions)
        await deliver_support_answers(self.bot, self.settings, self.sessions)
        self.bot.send_message.assert_awaited_once()
        assert self.bot.send_message.await_args.args[0] == 22
        async with self.sessions() as session:
            assert (await session.get(UserQuestion, self.question.id)).status == 'answered'

    async def test_uncertain_answer_requires_review_and_never_blindly_retries(self):
        self.bot.send_message.side_effect = TelegramNetworkError(method=SendMessage(chat_id=22, text='test'), message='response lost')
        async with self.sessions() as session:
            item = await session.get(UserQuestion, self.question.id)
            item.admin_answer, item.status = 'A saved answer', 'answer_pending'
            await session.commit()
        await deliver_support_answers(self.bot, self.settings, self.sessions)
        await deliver_support_answers(self.bot, self.settings, self.sessions)
        assert self.bot.send_message.await_count == 1
        async with self.sessions() as session:
            assert (await session.get(UserQuestion, self.question.id)).status == 'answer_review'

    async def test_native_reply_commits_before_transport_and_stale_editor_cannot_overwrite(self):
        await self.state.set_state(SupportAnswer.text)
        await self.state.update_data(support_question_id=self.question.id)
        message = SimpleNamespace(from_user=SimpleNamespace(id=11), text='Approved response', answer=AsyncMock())
        with patch('app.handlers.admin.support_bot.deliver_support_answers', AsyncMock()):
            async with self.sessions() as session:
                await support_answer(message, await session.get(User, self.admin.id), self.settings, session, self.state, self.bot)
            await self.state.set_state(SupportAnswer.text)
            await self.state.update_data(support_question_id=self.question.id)
            message.text = 'Stale response'
            async with self.sessions() as session:
                await support_answer(message, await session.get(User, self.admin.id), self.settings, session, self.state, self.bot)
        async with self.sessions() as session:
            item = await session.get(UserQuestion, self.question.id)
            assert item.admin_answer == 'Approved response' and item.status == 'answer_pending'
            assert await session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'support.answered')) == 1

    async def test_participant_cannot_reply_by_forging_fsm_or_callback(self):
        await self.state.set_state(SupportAnswer.text)
        await self.state.update_data(support_question_id=self.question.id)
        message = SimpleNamespace(from_user=SimpleNamespace(id=22), text='Forged response', answer=AsyncMock())
        async with self.sessions() as session:
            await support_answer(message, await session.get(User, self.member.id), self.settings, session, self.state, self.bot)
            assert (await session.get(UserQuestion, self.question.id)).admin_answer is None
        self.bot.send_message.assert_not_awaited()
