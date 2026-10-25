"""Delegation is capability-specific, global-only, revocable, and rollout-bound."""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import AppSetting, PermissionGrant, SupportMessage, User, UserQuestion
from app.handlers.admin.rights_block6 import toggle_support_category_permission
from app.handlers.admin.support_bot import show_inbox
from app.services.staff_access_service import (can_operate_queue,
    can_edit_literature, can_manage_literature_settings,
    can_operate_support_category, support_category_scope_id)
from app.services.support_service import (support_thread, support_assignees, support_attachment,
    update_support_thread, deliver_support_thread_messages)
from app.utils.constants import ApplicationStatus, Role


class StaffQueueAccessTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token='0000000000:CITESTTOKEN', feature_support_threads='ALL')

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_unrelated_and_scoped_grants_do_not_open_global_queue(self):
        async with self.factory() as session:
            admin = User(telegram_id=1, first_name='Admin', role=Role.ADMIN,
                         application_status=ApplicationStatus.APPROVED)
            staff = User(telegram_id=2, first_name='Staff', application_status=ApplicationStatus.APPROVED)
            session.add_all([admin, staff])
            await session.flush()
            grant = PermissionGrant(user_id=staff.id, permission='support.manage', scope_type='department',
                                    scope_id=7, granted_by=admin.id, is_active=True)
            session.add(grant)
            await session.flush()
            self.assertFalse(await can_operate_queue(session, staff, self.settings, 'support.manage'))
            grant.scope_type, grant.scope_id = 'global', 7
            await session.flush()
            self.assertFalse(await can_operate_queue(session, staff, self.settings, 'support.manage'))
            grant.scope_type, grant.scope_id = 'global', 0
            await session.flush()
            self.assertTrue(await can_operate_queue(session, staff, self.settings, 'support.manage'))
            self.assertFalse(await can_operate_queue(session, staff, self.settings, 'literature.manage'))
            grant.is_active = False
            await session.flush()
            self.assertFalse(await can_operate_queue(session, staff, self.settings, 'support.manage'))

    async def test_delegated_support_is_available_only_inside_rollout(self):
        async with self.factory() as session:
            staff = User(telegram_id=2, first_name='Staff', application_status=ApplicationStatus.APPROVED)
            owner = User(telegram_id=3, first_name='Owner', application_status=ApplicationStatus.APPROVED)
            session.add_all([staff, owner])
            await session.flush()
            grant = PermissionGrant(user_id=staff.id, permission='support.manage', scope_type='global',
                                    scope_id=0, granted_by=owner.id, is_active=True)
            item = UserQuestion(user_id=owner.id, text='Question')
            session.add_all([grant, item])
            await session.flush()
            self.assertEqual((await support_thread(session, item.id, staff.id, self.settings, staff=True)).id, item.id)
            self.assertIn(staff.id, [u.id for u in await support_assignees(session, self.settings)])
            self.settings.feature_support_threads = 'TESTERS'
            self.settings.support_thread_tester_ids = [99]
            self.assertFalse(await can_operate_queue(session, staff, self.settings, 'support.manage'))
            self.settings.support_thread_tester_ids = [2, 3]
            self.assertTrue(await can_operate_queue(session, staff, self.settings, 'support.manage'))
            self.settings.feature_support_threads = 'OFF'
            with self.assertRaises(PermissionError):
                await support_thread(session, item.id, staff.id, self.settings, staff=True)
            self.assertEqual(await support_assignees(session, self.settings), [])
            self.assertFalse(await can_operate_queue(session, staff, self.settings, 'support.manage'))

    async def test_category_grant_limits_lists_cards_actions_and_revokes_immediately(self):
        async with self.factory() as session:
            admin = User(telegram_id=10, first_name='Admin', role=Role.ADMIN,
                         application_status=ApplicationStatus.APPROVED)
            staff = User(telegram_id=20, first_name='Scoped', application_status=ApplicationStatus.APPROVED)
            owner = User(telegram_id=30, first_name='Owner', application_status=ApplicationStatus.APPROVED)
            session.add_all([admin, staff, owner])
            await session.flush()
            grant = PermissionGrant(user_id=staff.id, permission='support.manage',
                scope_type='support_category', scope_id=support_category_scope_id('events'),
                granted_by=admin.id, is_active=True)
            events = UserQuestion(user_id=owner.id, text='Event issue', category='events', file_id='private-file')
            projects = UserQuestion(user_id=owner.id, text='Project issue', category='projects')
            session.add_all([grant, events, projects])
            await session.flush()
            attachment = SupportMessage(question_id=events.id, author_id=owner.id,
                direction='participant', source_key='category-scope-test', text='File', file_id='file-id')
            session.add(attachment)
            await session.flush()

            # The staff entry point is visible, but it is not a global grant.
            self.assertTrue(await can_operate_queue(session, staff, self.settings, 'support.manage'))
            self.assertTrue(await can_operate_support_category(session, staff, self.settings, 'events'))
            self.assertFalse(await can_operate_support_category(session, staff, self.settings, 'projects'))
            self.assertEqual((await support_thread(session, events.id, staff.id,
                self.settings, staff=True)).id, events.id)
            message = SimpleNamespace(chat=SimpleNamespace(id=staff.telegram_id), answer=AsyncMock())
            await show_inbox(message, session, staff, self.settings)
            markup = message.answer.await_args.kwargs['reply_markup']
            callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
            self.assertIn(f'admin:support:item:{events.id}', callbacks)
            self.assertNotIn(f'admin:support:item:{projects.id}', callbacks)
            self.assertEqual(await support_attachment(session, self.settings, question_id=events.id,
                message_id=attachment.id, actor_id=staff.id, staff=True), 'file-id')
            with self.assertRaises(PermissionError):
                await support_thread(session, projects.id, staff.id, self.settings, staff=True)
            with self.assertRaises(PermissionError):
                await support_attachment(session, self.settings, question_id=projects.id,
                    message_id=attachment.id, actor_id=staff.id, staff=True)
            with self.assertRaises(PermissionError):
                await update_support_thread(session, self.settings, question_id=events.id,
                    actor_id=staff.id, expected_revision=0, action='category', category='projects')
            with self.assertRaises(PermissionError):
                await update_support_thread(session, self.settings, question_id=events.id,
                    actor_id=staff.id, expected_revision=0, action='assign', assignee_id=owner.id)

            grant.is_active = False
            await session.flush()
            self.assertFalse(await can_operate_queue(session, staff, self.settings, 'support.manage'))
            with self.assertRaises(PermissionError):
                await support_thread(session, events.id, staff.id, self.settings, staff=True)

    async def test_literature_scope_allows_editorial_items_but_not_module_settings(self):
        async with self.factory() as session:
            admin = User(telegram_id=40, first_name='Admin', role=Role.ADMIN,
                         application_status=ApplicationStatus.APPROVED)
            editor = User(telegram_id=50, first_name='Editor', application_status=ApplicationStatus.APPROVED)
            session.add_all([admin, editor])
            await session.flush()
            grant = PermissionGrant(user_id=editor.id, permission='literature.manage',
                scope_type='literature_category', scope_id=1, granted_by=admin.id, is_active=True)
            session.add(grant)
            await session.flush()
            self.assertTrue(await can_operate_queue(session, editor, self.settings, 'literature.manage'))
            self.assertTrue(await can_edit_literature(session, editor, self.settings))
            self.assertFalse(await can_manage_literature_settings(session, editor, self.settings))
            grant.is_active = False
            await session.flush()
            self.assertFalse(await can_edit_literature(session, editor, self.settings))

    async def test_delivery_rechecks_current_category_and_partial_revocation(self):
        for index, scenario in enumerate(('allowed', 'moved', 'revoked')):
            with self.subTest(scenario=scenario):
                async with self.factory() as session:
                    offset = index * 100
                    admin = User(telegram_id=10 + offset, first_name='Admin', role=Role.ADMIN,
                        application_status=ApplicationStatus.APPROVED)
                    staff = User(telegram_id=20 + offset, first_name='Scoped',
                        application_status=ApplicationStatus.APPROVED)
                    owner = User(telegram_id=30 + offset, first_name='Owner',
                        application_status=ApplicationStatus.APPROVED)
                    session.add_all([admin, staff, owner])
                    await session.flush()
                    events = PermissionGrant(user_id=staff.id, permission='support.manage',
                        scope_type='support_category', scope_id=support_category_scope_id('events'),
                        granted_by=admin.id, is_active=scenario != 'revoked')
                    projects = PermissionGrant(user_id=staff.id, permission='support.manage',
                        scope_type='support_category', scope_id=support_category_scope_id('projects'),
                        granted_by=admin.id, is_active=True)
                    item = UserQuestion(user_id=owner.id, text='Question',
                        category='general' if scenario == 'moved' else 'events', assigned_to=staff.id)
                    session.add_all([events, projects, item])
                    await session.flush()
                    key = f'support-assignment:scope-{index}'
                    session.add(AppSetting(key=key, value={'question_id': item.id, 'assignee_id': staff.id}))
                    session.add(SupportMessage(question_id=item.id, author_id=owner.id,
                        direction='participant', source_key=f'scope-delivery-{index}', text='Followup',
                        delivery_status='pending'))
                    await session.commit()
                    # Another valid category must not authorize this ticket.
                    self.assertTrue(await can_operate_queue(session, staff, self.settings, 'support.manage'))
                    admin_tg, staff_tg = admin.telegram_id, staff.telegram_id
                send = AsyncMock(return_value=SimpleNamespace(status='sent', attempt_count=1))
                with patch('app.services.support_service.safe_send_once', send), patch(
                        'app.services.support_service.admin_notification_recipients',
                        AsyncMock(return_value={admin_tg})):
                    await deliver_support_thread_messages(None, self.settings, self.factory)
                    await deliver_support_thread_messages(None, self.settings, self.factory)
                recipients = [call.args[2] for call in send.await_args_list]
                self.assertEqual(recipients, [staff_tg, staff_tg] if scenario == 'allowed' else [admin_tg])
                async with self.factory() as session:
                    self.assertIsNone(await session.scalar(select(AppSetting).where(AppSetting.key == key)))

    async def test_category_callback_toggles_grant_and_preserves_literature_indicator(self):
        async with self.factory() as session:
            admin = User(telegram_id=1000, first_name='Admin', role=Role.ADMIN,
                application_status=ApplicationStatus.APPROVED)
            target = User(telegram_id=1001, first_name='Editor',
                application_status=ApplicationStatus.APPROVED)
            session.add_all([admin, target])
            await session.flush()
            literature = PermissionGrant(user_id=target.id, permission='literature.manage',
                scope_type='literature_category', scope_id=1, granted_by=admin.id, is_active=True)
            session.add(literature)
            await session.commit()
            scope = support_category_scope_id('events')
            call = SimpleNamespace(data=f'admin:permission:support_category_toggle:{target.id}:{scope}',
                message=SimpleNamespace(answer=AsyncMock(), edit_reply_markup=AsyncMock()))
            for enabled in (True, False):
                with patch('app.handlers.admin.rights_block6._guard', AsyncMock(return_value=True)):
                    await toggle_support_category_permission(call, admin, self.settings, session)
                grant = await session.scalar(select(PermissionGrant).where(
                    PermissionGrant.user_id == target.id, PermissionGrant.permission == 'support.manage'))
                self.assertEqual(grant.is_active, enabled)
                markup = call.message.edit_reply_markup.await_args.kwargs['reply_markup']
                button = next(button for row in markup.inline_keyboard for button in row
                    if button.callback_data == f'admin:permission:literature_toggle:{target.id}')
                self.assertTrue(button.text.startswith('✅'))
                await session.refresh(literature)
                self.assertTrue(literature.is_active)
