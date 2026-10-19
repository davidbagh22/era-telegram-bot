"""Delegation is capability-specific, global-only, revocable, and rollout-bound."""
from unittest import IsolatedAsyncioTestCase

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import PermissionGrant, User, UserQuestion
from app.services.staff_access_service import can_operate_queue
from app.services.support_service import support_thread, support_assignees
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
            self.settings.feature_support_threads = 'OFF'
            with self.assertRaises(PermissionError):
                await support_thread(session, item.id, staff.id, self.settings, staff=True)
            self.assertEqual(await support_assignees(session, self.settings), [])
