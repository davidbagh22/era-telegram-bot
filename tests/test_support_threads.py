from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SendMessage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import SupportMessage, User, UserQuestion
from app.database.system_models import NotificationDelivery
from app.handlers.support_thread_views import show_my_support, show_support_thread
from app.services.scheduler_service import deliver_support_answers, send_review_sla_reminders
from app.services.support_service import append_support_message, support_thread, update_support_thread
from app.utils.constants import ApplicationStatus, Role


class SupportThreadTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token='0000000000:SUPPORTTEST', feature_support_threads='ALL',
            feature_review_reminders='ALL')
        self.bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=12)))
        for target, value in (
            ('app.services.notification_service._session_factory', lambda *_: self.sessions),
            ('app.services.support_service.admin_notification_recipients', AsyncMock(return_value={11})),
            ('app.services.scheduler_service.admin_notification_recipients', AsyncMock(return_value={11, 12})),
        ):
            mock = patch(target, value)
            mock.start()
            self.addCleanup(mock.stop)
        async with self.sessions() as session:
            staff = User(telegram_id=11, first_name='Admin', role=Role.ADMIN, application_status=ApplicationStatus.APPROVED)
            other_staff = User(telegram_id=12, first_name='Admin 2', role=Role.ADMIN, application_status=ApplicationStatus.APPROVED)
            member = User(telegram_id=22, first_name='Member', application_status=ApplicationStatus.APPROVED)
            stranger = User(telegram_id=33, first_name='Stranger', application_status=ApplicationStatus.APPROVED)
            session.add_all([staff, other_staff, member, stranger])
            await session.flush()
            self.staff, self.other_staff, self.member, self.stranger = staff.id, other_staff.id, member.id, stranger.id
            item = UserQuestion(user_id=member.id, text='Original', file_id='photo-file')
            session.add(item)
            await session.commit()
            self.item = item.id

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def append(self, text='Ответ', *, staff=True, source='11:1', revision=None, actor_id=None):
        async with self.sessions() as session:
            item = await session.get(UserQuestion, self.item)
            message, created = await append_support_message(session, self.settings, question_id=item.id,
                actor_id=actor_id or (self.staff if staff else self.member), staff=staff, text=text, source_key=source,
                expected_revision=item.thread_revision if revision is None else revision)
            await session.commit()
            return message.id, created

    async def test_same_webhook_stores_one_reply_and_legacy_original_once(self):
        first = await self.append(revision=0)
        again = await self.append(revision=0)
        assert first[0] == again[0] and first[1] and not again[1]
        async with self.sessions() as session:
            rows = (await session.scalars(select(SupportMessage).order_by(SupportMessage.id))).all()
            assert [r.text for r in rows] == ['Original', 'Ответ']
            assert rows[0].file_id == 'photo-file' and rows[0].delivery_status == 'legacy'
            assert (await session.get(UserQuestion, self.item)).text == 'Original'

    async def test_stale_second_admin_reply_does_not_overwrite_history(self):
        await self.append(revision=0)
        with self.assertRaisesRegex(ValueError, 'stale_thread'):
            await self.append(text='Different answer', source='12:2', revision=0, actor_id=self.other_staff)
        async with self.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(SupportMessage)) == 2

    async def test_same_text_in_another_round_is_delivered_as_another_message(self):
        await self.append(source='11:1')
        await deliver_support_answers(self.bot, self.settings, self.sessions)
        await self.append('Дополнение', staff=False, source='22:2')
        await self.append(source='11:3')
        await deliver_support_answers(self.bot, self.settings, self.sessions)
        await deliver_support_answers(self.bot, self.settings, self.sessions)
        replies = [c for c in self.bot.send_message.await_args_list if c.args[0] == 22]
        assert len(replies) == 2 and replies[0].args[1] == replies[1].args[1]
        async with self.sessions() as session:
            receipts = (await session.scalars(select(NotificationDelivery).where(
                NotificationDelivery.notification_type == 'support_thread'))).all()
            assert len(receipts) == 3 and all(r.status == 'sent' and r.attempt_count == 1 for r in receipts)

    async def test_stranger_cannot_read_reply_or_claim_another_ticket(self):
        async with self.sessions() as session:
            for staff in (False, True):
                with self.assertRaises(PermissionError):
                    await support_thread(session, self.item, self.stranger, self.settings, staff=staff)
            with self.assertRaises(PermissionError):
                await append_support_message(session, self.settings, question_id=self.item, actor_id=self.stranger,
                    staff=False, text='Forged', source_key='33:3', expected_revision=0)
            assert await session.scalar(select(func.count()).select_from(SupportMessage)) == 0

    async def test_fresh_database_permissions_reject_a_blocked_stale_profile(self):
        async with self.sessions() as session:
            (await session.get(User, self.staff)).is_blocked = True
            await session.commit()
        with self.assertRaises(PermissionError):
            await self.append()

    async def test_rollout_uses_explicit_testers_and_off_rejects_mutation(self):
        self.settings.feature_support_threads = 'TESTERS'
        with self.assertRaises(PermissionError):
            await self.append()
        self.settings.feature_tester_ids = [11]
        with self.assertRaises(PermissionError):
            await self.append()
        self.settings.feature_tester_ids = [11, 22]
        await self.append()
        self.settings.feature_support_threads = 'OFF'
        with self.assertRaises(PermissionError):
            await self.append(source='11:2')
        # Already committed work still drains after rollback of the feature.
        await deliver_support_answers(self.bot, self.settings, self.sessions)
        assert self.bot.send_message.await_count == 1

    async def test_claim_category_close_reopen_are_versioned_and_preserve_history(self):
        async with self.sessions() as session:
            item = await update_support_thread(session, self.settings, question_id=self.item, actor_id=self.staff,
                expected_revision=0, action='claim')
            await session.commit()
            revision = item.thread_revision
            assert item.assigned_to == self.staff
        async with self.sessions() as session:
            with self.assertRaisesRegex(ValueError, 'already_assigned'):
                await update_support_thread(session, self.settings, question_id=self.item, actor_id=self.other_staff,
                    expected_revision=revision, action='claim')
            await session.rollback()
        for action, category in [('category', 'events'), ('close', None), ('reopen', None)]:
            async with self.sessions() as session:
                item = await update_support_thread(session, self.settings, question_id=self.item, actor_id=self.staff,
                    expected_revision=revision, action=action, category=category)
                await session.commit()
                revision = item.thread_revision
                if action == 'close':
                    with self.assertRaisesRegex(ValueError, 'closed_thread'):
                        await self.append(staff=False, source='22:4')
        async with self.sessions() as session:
            item = await session.get(UserQuestion, self.item)
            assert item.category == 'events' and item.waiting_since and item.status == 'thread_waiting'
            assert await session.scalar(select(func.count()).select_from(SupportMessage)) == 1

    async def test_legacy_answer_in_flight_is_not_migrated_or_rekeyed(self):
        async with self.sessions() as session:
            item = await session.get(UserQuestion, self.item)
            item.status, item.admin_answer = 'answer_pending', 'Old answer'
            await session.commit()
        with self.assertRaisesRegex(ValueError, 'legacy_delivery_pending'):
            await self.append()
        await deliver_support_answers(self.bot, self.settings, self.sessions)
        await self.append('Next answer', source='11:8')
        await deliver_support_answers(self.bot, self.settings, self.sessions)
        assert self.bot.send_message.await_count == 2
        async with self.sessions() as session:
            rows = (await session.scalars(select(SupportMessage).order_by(SupportMessage.id))).all()
            assert [r.text for r in rows] == ['Original', 'Old answer', 'Next answer']

    async def test_uncertain_delivery_is_not_blindly_retried_after_restart(self):
        await self.append()
        self.bot.send_message.side_effect = TelegramNetworkError(method=SendMessage(chat_id=22, text='x'), message='network')
        await deliver_support_answers(self.bot, self.settings, self.sessions)
        await deliver_support_answers(self.bot, self.settings, self.sessions)
        assert self.bot.send_message.await_count == 1
        async with self.sessions() as session:
            row = await session.scalar(select(SupportMessage).where(SupportMessage.direction == 'staff'))
            assert row.delivery_status == 'uncertain'

    async def test_followups_do_not_postpone_sla_and_reminders_stop_on_answer(self):
        await self.append(staff=False, text='Follow up', source='22:1')
        async with self.sessions() as session:
            item = await session.get(UserQuestion, self.item)
            item.waiting_since = datetime.now(timezone.utc) - timedelta(hours=25)
            item.assigned_to = self.staff
            await session.commit()
            started = item.waiting_since
        await self.append(staff=False, text='One more detail', source='22:2')
        async with self.sessions() as session:
            item = await session.get(UserQuestion, self.item)
            assert item.waiting_since.replace(tzinfo=timezone.utc) == started
        await send_review_sla_reminders(self.bot, self.settings, self.sessions)
        await send_review_sla_reminders(self.bot, self.settings, self.sessions)
        assert self.bot.send_message.await_count == 1 and self.bot.send_message.await_args.args[0] == 11
        await self.append(source='11:2')
        await send_review_sla_reminders(self.bot, self.settings, self.sessions,
            now=datetime.now(timezone.utc)+timedelta(days=3))
        assert self.bot.send_message.await_count == 1

    async def test_owner_history_is_paginated_and_does_not_show_other_tickets(self):
        async with self.sessions() as session:
            session.add(UserQuestion(user_id=self.stranger, text='Secret stranger question'))
            await session.commit()
            message = SimpleNamespace(answer=AsyncMock())
            await show_my_support(message, session, await session.get(User, self.member))
            assert '· 1' in message.answer.await_args.args[0]
            assert 'Secret stranger' not in str(message.answer.await_args_list)
        await self.append('First answer')
        async with self.sessions() as session:
            await show_support_thread(message, session, self.settings, question_id=self.item, actor_id=self.member)
            text = message.answer.await_args.args[0]
            assert 'Original' in text and 'First answer' in text and 'Администратор' in text
