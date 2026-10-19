import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import Department, PermissionGrant, Task, TaskSubmission, User
from app.services.admin_analytics_service import build_scoped_leader_operations


class ScopedLeaderAnalyticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_scope_revocation_and_plain_leader_are_enforced(self):
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        settings = Settings(bot_token='0000000000:LOCALTEST', admin_ids=[1001])
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            admin = User(telegram_id=1001, first_name='Admin', role='admin', application_status='approved')
            head = User(telegram_id=1002, first_name='Head', role='participant', application_status='approved')
            leader = User(telegram_id=1003, first_name='Leader', role='leader', application_status='approved')
            one, two = Department(name='One'), Department(name='Two')
            session.add_all([admin, head, leader, one, two]); await session.flush()
            grant = PermissionGrant(user_id=head.id, permission='tasks.manage', scope_type='department', scope_id=one.id, granted_by=admin.id)
            session.add(grant)
            now = datetime.now(timezone.utc)
            for department, status, deadline in [(one, 'in_progress', now-timedelta(days=1)), (one, 'review', None), (one, 'completed', None), (two, 'in_progress', None)]:
                session.add(Task(title='Fixture', description='Fixture', creator_id=admin.id, assignee_id=leader.id,
                                 department_id=department.id, status=status, deadline=deadline))
            public = Task(title='Public result', description='Fixture', creator_id=admin.id, assignee_id=leader.id,
                          department_id=one.id, status='published')
            session.add(public); await session.flush()
            session.add(TaskSubmission(task_id=public.id, user_id=leader.id, status='pending'))
            await session.commit()
            own = await build_scoped_leader_operations(session, head, settings, now=now)
            assert (own.active_tasks, own.completed_tasks, own.overdue_tasks, own.awaiting_review) == (3, 1, 1, 2)
            assert own.workload == (('Leader', 3),)
            whole = await build_scoped_leader_operations(session, admin, settings, now=now)
            assert whole.active_tasks == 4
            with self.assertRaises(PermissionError):
                await build_scoped_leader_operations(session, leader, settings, now=now)
            grant.is_active = False
            await session.commit()
            with self.assertRaises(PermissionError):
                await build_scoped_leader_operations(session, head, settings, now=now)
        await engine.dispose()
