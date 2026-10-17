from datetime import datetime, timedelta, timezone
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
from app.database.chat_moderation import PendingChatJoinRequest
from app.database.models import AppSetting, AuditLog, PointTransaction, User
from app.handlers.admin.application_review_bot import application_action, application_comment
from app.handlers.admin.dashboard_block_a import _show_application_list
from app.keyboards.bot_shell import main_inline_keyboard, main_reply_keyboard
from app.services.application_review_service import application_review_version, deliver_application_notices
from app.utils.constants import ApplicationStatus, Role


def buttons(markup):
    rows = markup.inline_keyboard if hasattr(markup, 'inline_keyboard') else markup.keyboard
    return [button for row in rows for button in row]


def test_admin_has_native_shortcuts_even_with_the_app_enabled():
    for miniapp_url in ('', 'https://era.example/app/'):
        labels = {b.text for b in buttons(main_reply_keyboard(miniapp_url, admin=True))}
        assert {'📊 Статистика', '📥 Заявки'} <= labels
        inline = buttons(main_inline_keyboard(miniapp_url=miniapp_url, admin=True))
        assert {'admin:applications', 'admin:management:open'} <= {b.callback_data for b in inline}
        assert not any(b.text == '📥 Заявки' for b in buttons(main_reply_keyboard(miniapp_url)))
        if miniapp_url:
            assert any(b.web_app and b.text == '🔥 Открыть ЭРА' for b in inline)


class NativeAdminTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token='1234567890:test', feature_management_reports='TESTERS',
                                 management_report_recipient_ids=[999], miniapp_auth_secret='test',
                                 miniapp_url='https://era.example/app/')
        self.bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=20)))
        self.state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=11, user_id=11))
        self.factory_patch = patch('app.services.notification_service._session_factory', return_value=self.sessions)
        self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)
        async with self.sessions() as session:
            self.admin = User(telegram_id=11, first_name='Admin', role=Role.ADMIN,
                              application_status=ApplicationStatus.APPROVED)
            self.applicant = User(telegram_id=22, first_name='Applicant', application_status=ApplicationStatus.PENDING,
                                  personal_data_consent=True)
            session.add_all([self.admin, self.applicant])
            await session.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    def call(self, action='approve', revision=0, *, actor=11):
        return SimpleNamespace(data=f'admin:application_action:{action}:{self.applicant.id}:{revision}',
                               from_user=SimpleNamespace(id=actor), answer=AsyncMock(),
                               message=SimpleNamespace(answer=AsyncMock()))

    async def test_native_queue_paginates_all_applications_and_omits_archived_records(self):
        now = datetime.now(timezone.utc)
        async with self.sessions() as session:
            for i in range(10):
                session.add(User(telegram_id=100+i, first_name=f'Pending {i}', created_at=now+timedelta(seconds=i)))
            session.add(User(telegram_id=999, first_name='Archived private', is_archived=True))
            await session.commit()
            message = SimpleNamespace(answer=AsyncMock())
            await _show_application_list(message, session, page=0)
            text, = message.answer.await_args.args
            keyboard = message.answer.await_args.kwargs['reply_markup']
            assert '· 11' in text
            assert len([b for b in buttons(keyboard) if (b.callback_data or '').startswith('admin:application:')]) == 8
            await _show_application_list(message, session, page=1)
            keyboard = message.answer.await_args.kwargs['reply_markup']
            assert len([b for b in buttons(keyboard) if (b.callback_data or '').startswith('admin:application:')]) == 3
            assert 'Archived private' not in str(keyboard)

    async def test_approval_is_durable_and_double_click_cannot_repeat_points_or_message(self):
        call = self.call()
        async with self.sessions() as session:
            admin = await session.get(User, self.admin.id)
            await application_action(call, admin, self.settings, session, self.state, self.bot)
        async with self.sessions() as session:
            await application_action(self.call(), await session.get(User, self.admin.id),
                                     self.settings, session, self.state, self.bot)
            assert (await session.get(User, self.applicant.id)).application_status == ApplicationStatus.APPROVED
            assert await session.scalar(select(func.count()).select_from(PointTransaction).where(
                PointTransaction.idempotency_key == f'registration_approval:{self.applicant.id}')) == 1
            assert await session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'user.approved')) == 1
        assert self.bot.send_message.await_count == 1

    async def test_rejection_requires_comment_and_preserves_explicit_reason(self):
        call = self.call('reject')
        async with self.sessions() as session:
            admin = await session.get(User, self.admin.id)
            await application_action(call, admin, self.settings, session, self.state, self.bot)
            assert (await session.get(User, self.applicant.id)).application_status == ApplicationStatus.PENDING
            message = SimpleNamespace(from_user=SimpleNamespace(id=11), text='Нужно дополнить опыт', answer=AsyncMock())
            await application_comment(message, admin, self.settings, session, self.state, self.bot)
        async with self.sessions() as session:
            target = await session.get(User, self.applicant.id)
            assert target.application_status == ApplicationStatus.REJECTED
            decision = await session.scalar(select(AuditLog).where(AuditLog.action == 'user.rejected'))
            assert decision.new_value['comment'] == message.text
        assert message.text in self.bot.send_message.await_args.args[1]
        assert await self.state.get_state() is None

    async def test_native_approval_accepts_pending_chat_request_and_persists_access(self):
        self.bot.approve_chat_join_request = AsyncMock(return_value=True)
        async with self.sessions() as session:
            session.add(PendingChatJoinRequest(chat_id=-100123, user_id=22, chat_key='general'))
            await session.commit()
            await application_action(self.call(), await session.get(User, self.admin.id),
                                     self.settings, session, self.state, self.bot)
        async with self.sessions() as session:
            request = await session.scalar(select(PendingChatJoinRequest))
            assert request.status == 'approved'
        self.bot.approve_chat_join_request.assert_awaited_once_with(chat_id=-100123, user_id=22)
        self.bot.send_message.assert_awaited_once()

    async def test_access_failure_is_retried_after_restart_with_a_bound(self):
        from aiogram.exceptions import TelegramForbiddenError
        from aiogram.methods import ApproveChatJoinRequest
        self.bot.approve_chat_join_request = AsyncMock(side_effect=TelegramForbiddenError(
            method=ApproveChatJoinRequest(chat_id=-100123, user_id=22), message='not enough rights'))
        async with self.sessions() as session:
            session.add(PendingChatJoinRequest(chat_id=-100123, user_id=22, chat_key='general'))
            await session.commit()
            await application_action(self.call(), await session.get(User, self.admin.id),
                                     self.settings, session, self.state, self.bot)
        for _ in range(4):
            await deliver_application_notices(self.bot, self.settings, self.sessions)
        assert self.bot.approve_chat_join_request.await_count == 3
        self.bot.send_message.assert_awaited_once()
        async with self.sessions() as session:
            assert (await session.get(User, self.applicant.id)).application_status == ApplicationStatus.APPROVED
            assert (await session.scalar(select(PendingChatJoinRequest))).status == 'pending'

    async def test_restarted_worker_delivers_committed_notice_once(self):
        from app.services.application_review_service import request_more_info, stage_application_notice
        async with self.sessions() as session:
            target = await session.get(User, self.applicant.id)
            await request_more_info(session, target, actor_id=self.admin.id, comment='Уточните город')
            await stage_application_notice(session, target, text='Уточните город')
            await session.commit()
        await deliver_application_notices(self.bot, self.settings, self.sessions)
        await deliver_application_notices(self.bot, self.settings, self.sessions)
        assert self.bot.send_message.await_count == 1
        async with self.sessions() as session:
            assert await session.scalar(select(AppSetting).where(AppSetting.key.like('application-notice:%'))) is None

    async def test_participant_forgery_cannot_review_and_stale_version_cannot_overwrite(self):
        async with self.sessions() as session:
            member = await session.get(User, self.applicant.id)
            call = self.call(actor=22)
            await application_action(call, member, self.settings, session, self.state, self.bot)
            assert (await session.get(User, member.id)).application_status == ApplicationStatus.PENDING
            from app.services.application_review_service import request_more_info
            await request_more_info(session, member, actor_id=self.admin.id, comment='Уточните город')
            await session.commit()
            assert await application_review_version(session, member.id) > 0
            await application_action(self.call(), await session.get(User, self.admin.id), self.settings,
                                     session, self.state, self.bot)
            assert member.application_status == ApplicationStatus.NEEDS_INFO
        self.bot.send_message.assert_not_awaited()

    async def test_admin_can_open_report_without_being_an_automatic_delivery_recipient(self):
        from app.handlers.admin.commands_ready import management_report_command
        message = SimpleNamespace(from_user=SimpleNamespace(id=11), answer=AsyncMock())
        async with self.sessions() as session:
            await management_report_command(message, await session.get(User, self.admin.id), self.settings, session)
        text = message.answer.await_args.args[0]
        assert '<b>ЭРА · Админ-сводка</b>' in text
        assert message.answer.await_args.kwargs['parse_mode'] == 'HTML'
        assert any(b.web_app and b.text == '🔥 Открыть ЭРА'
                   for b in buttons(message.answer.await_args.kwargs['reply_markup']))
