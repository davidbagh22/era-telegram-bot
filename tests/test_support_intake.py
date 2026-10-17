from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import AppSetting, AuditLog, User, UserQuestion
from app.handlers.participant.questions import _save_question
from app.services.support_service import create_support_question, deliver_support_intake_notices
from app.utils.constants import ApplicationStatus, Role


class SupportIntakeTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token='1234567890:test')
        self.bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=9)))
        self.state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=22, user_id=22))
        self.factory_patch = patch('app.services.notification_service._session_factory', return_value=self.sessions)
        self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)
        self.admin_patch = patch('app.services.support_service.admin_notification_recipients', AsyncMock(return_value={11, -100123}))
        self.admin_patch.start()
        self.addCleanup(self.admin_patch.stop)
        async with self.sessions() as session:
            self.admin = User(telegram_id=11, first_name='Admin', role=Role.ADMIN, application_status=ApplicationStatus.APPROVED)
            self.member = User(telegram_id=22, first_name='Member', application_status=ApplicationStatus.APPROVED)
            session.add_all([self.admin, self.member])
            await session.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_duplicate_source_creates_one_question_audit_and_notice(self):
        async with self.sessions() as session:
            first, created = await create_support_question(session, user_id=self.member.id,
                source_key='22:8', text='A private question')
            assert created
            await session.commit()
            second, created = await create_support_question(session, user_id=self.member.id,
                source_key='22:8', text='A private question')
            assert not created and second.id == first.id
            await session.commit()
            assert await session.scalar(select(func.count()).select_from(UserQuestion)) == 1
            assert await session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'question.created')) == 1
            assert await session.scalar(select(func.count()).select_from(AppSetting).where(AppSetting.key.like('support-intake-notice:%'))) == 1

    async def test_source_conflict_does_not_replace_existing_text(self):
        async with self.sessions() as session:
            item, _ = await create_support_question(session, user_id=self.member.id, source_key='22:8', text='Original')
            await session.commit()
            question_id = item.id
            with self.assertRaises(ValueError):
                await create_support_question(session, user_id=self.member.id, source_key='22:8', text='Changed')
            await session.rollback()
        async with self.sessions() as session:
            assert (await session.get(UserQuestion, question_id)).text == 'Original'

    async def test_stale_approved_user_cannot_submit_after_being_blocked(self):
        async with self.sessions() as session:
            stale = await session.get(User, self.member.id)
            async with self.sessions() as other:
                (await other.get(User, self.member.id)).is_blocked = True
                await other.commit()
            with self.assertRaises(PermissionError):
                await create_support_question(session, user_id=stale.id, source_key='22:8', text='Not allowed')
            assert await session.scalar(select(func.count()).select_from(UserQuestion)) == 0

    async def test_rollback_has_no_question_or_notification(self):
        async with self.sessions() as session:
            await create_support_question(session, user_id=self.member.id, source_key='22:8', text='Rolled back')
            await session.rollback()
        await deliver_support_intake_notices(self.bot, self.settings, self.sessions)
        self.bot.send_message.assert_not_awaited()
        async with self.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(UserQuestion)) == 0

    async def test_notice_failure_does_not_lose_question_and_restart_notifies_once_privately(self):
        await self.state.set_data({'question_text': 'Saved before Telegram', 'question_source': '22:8'})
        message = SimpleNamespace(chat=SimpleNamespace(id=22), message_id=9, answer=AsyncMock())
        with patch('app.handlers.participant.questions.deliver_support_intake_notices',
                   AsyncMock(side_effect=RuntimeError('simulated transport failure'))):
            async with self.sessions() as session:
                await _save_question(message, self.state, session, await session.get(User, self.member.id), self.bot, self.settings)
        async with self.sessions() as session:
            item = await session.scalar(select(UserQuestion))
            assert item.text == 'Saved before Telegram'
        assert f'#{item.id}' in message.answer.await_args.args[0]
        assert await self.state.get_state() is None
        assert await self.state.get_data() == {}
        await deliver_support_intake_notices(self.bot, self.settings, self.sessions)
        await deliver_support_intake_notices(self.bot, self.settings, self.sessions)
        self.bot.send_message.assert_awaited_once()
        call = self.bot.send_message.await_args
        assert call.args[0] == 11
        assert call.kwargs['reply_markup'].inline_keyboard[0][0].callback_data == f'admin:support:item:{item.id}'
