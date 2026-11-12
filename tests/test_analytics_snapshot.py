from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from unittest.mock import patch

import unittest
import pytest
from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AuditLog, Event, EventRegistration, LeadershipAttentionItem, PointTransaction, Project, Task, TaskSubmission, User
from app.services.analytics_snapshot_service import build_analytics_snapshot, count_new_members
from app.services.excel_service import build_analytics_workbook
from app.services.admin_dashboard_service import dashboard_metrics
from app.services.organization_health_service import build_organization_health
from app.services.era_efficiency_service import build_efficiency_snapshot


class AnalyticsSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_verified_periods_retention_and_excel_share_values(self):
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            users = [User(telegram_id=i, first_name=str(i), application_status='approved', is_archived=(i == 4)) for i in range(1, 5)]
            session.add_all(users)
            await session.flush()
            # Returning verified user, digital-only user, zero-point attendee and archived user.
            for n, days, source in [(0, 5, 'task_completion'), (0, 35, 'task_completion'), (1, 2, 'digital_engagement'), (3, 3, 'event_attendance')]:
                session.add(PointTransaction(user_id=users[n].id, points=10, reason='fixture', source_type=source, created_at=now-timedelta(days=days)))
            event = Event(title='fixture', description='fixture', event_date=date(2026, 10, 17), event_time=time(12), location='online', format='online', created_by=users[0].id)
            session.add(event)
            await session.flush()
            session.add(EventRegistration(event_id=event.id, user_id=users[2].id, status='attended', last_confirmation_at=now-timedelta(days=3)))
            session.add(AuditLog(action='user.approved', entity_type='user', entity_id=users[0].id, created_at=now-timedelta(days=6)))
            session.add(Task(title='one', description='fixture', creator_id=users[0].id, status='review', deadline=now-timedelta(days=2)))
            public = Task(title='Public', description='fixture', creator_id=users[0].id, status='published')
            session.add(public)
            await session.flush()
            session.add(TaskSubmission(task_id=public.id, user_id=users[0].id, status='pending'))
            await session.commit()
            snapshot = await build_analytics_snapshot(session, now=now)
            metrics = {m.key: m for m in snapshot.metrics}
            assert metrics['members'].value == 3
            assert metrics['active'].value == 2
            assert metrics['active'].previous == 1
            assert metrics['retention'].value == 100
            assert metrics['new_members'].value == 1
            assert metrics['attention'].value == 2
            assert metrics['members'].previous is None
            assert metrics['funnel'].value is None
            workbook = load_workbook(BytesIO(build_analytics_workbook([], [], [], {}, snapshot=snapshot)))
            rows = list(workbook['Обзор 2.0'].values)[1:]
            assert [row[1] for row in rows] == [m.value for m in snapshot.metrics]
            # Snapshot accepts a fixed as_of, while these live views use the
            # wall clock. Freeze all clocks to the fixture date so the 14-day
            # cohort does not drift as CI runs on later calendar days.
            class FixtureDatetime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return now.astimezone(tz) if tz else now.replace(tzinfo=None)

            class FixtureDate(date):
                @classmethod
                def today(cls):
                    return now.date()

            with (
                patch('app.services.admin_dashboard_service.datetime', FixtureDatetime),
                patch('app.services.organization_health_service.datetime', FixtureDatetime),
                patch('app.services.organization_health_service.date', FixtureDate),
                patch('app.services.era_efficiency_service.datetime', FixtureDatetime),
                patch('app.services.era_efficiency_service.date', FixtureDate),
            ):
                dashboard = await dashboard_metrics(session)
                assert dashboard.values['active_base'] == 2
                health = await build_organization_health(session)
                assert next(m for m in health.metrics if m.key == 'active_30d').value == 2
                efficiency = await build_efficiency_snapshot(session)
                assert efficiency is not None
            for days in (7, 90):
                assert (await build_analytics_snapshot(session, days=days, now=now)).days == days
            with pytest.raises(ValueError):
                await build_analytics_snapshot(session, days=8, now=now)
        await engine.dispose()
    
    
    async def test_empty_cohort_has_no_invented_retention(self):
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine)() as session:
            snapshot = await build_analytics_snapshot(session)
            assert next(m for m in snapshot.metrics if m.key == 'retention').value is None
        await engine.dispose()

    async def test_open_blockers_are_distinct_and_project_statuses_agree(self):
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            owner = User(telegram_id=99, first_name='Fixture', application_status='approved')
            session.add(owner); await session.flush()
            tasks = [Task(title=status, description='Fixture', creator_id=owner.id, status=status)
                     for status in ['in_progress', 'completed', 'cancelled', 'new']]
            session.add_all(tasks); await session.flush()
            for task in tasks:
                session.add(LeadershipAttentionItem(type='leaders_task', scope_type='task', scope_id=task.id,
                                                   status='resolved' if task.status == 'new' else 'open'))
            session.add(LeadershipAttentionItem(type='leaders_task', scope_type='task', scope_id=tasks[0].id, status='in_progress'))
            for status in ['approved', 'in_progress', 'draft', 'completed', 'cancelled']:
                session.add(Project(title=status, short_description='Fixture', author_id=owner.id, status=status))
            await session.commit()
            metrics = {m.key: m for m in (await build_analytics_snapshot(session)).metrics}
            assert metrics['attention'].value == 1
            assert metrics['projects'].value == 2
            assert (await dashboard_metrics(session)).values['projects_active'] == 2
            assert next(m.value for m in (await build_organization_health(session)).metrics if m.key == 'active_projects') == 2
            assert next(m.value for m in (await build_efficiency_snapshot(session)).metrics if m.key == 'projects') == 2
        await engine.dispose()


    async def test_new_member_boundaries_and_first_approval(self):
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
        async with async_sessionmaker(engine)() as session:
            people = [User(telegram_id=i, first_name='Fixture', application_status='approved') for i in (11, 12, 13)]
            session.add_all(people); await session.flush()
            for person, stamp in zip(people, [now-timedelta(days=30), now, now-timedelta(days=30, microseconds=1)]):
                session.add(AuditLog(action='user.approved', entity_type='user', entity_id=person.id, created_at=stamp))
            session.add(AuditLog(action='user.approved', entity_type='user', entity_id=people[2].id, created_at=now-timedelta(days=1)))
            await session.commit()
            assert await count_new_members(session, now-timedelta(days=30), now) == 1
            assert await count_new_members(session, now-timedelta(days=7), now) == 0
            assert await count_new_members(session, now-timedelta(days=90), now) == 2
        await engine.dispose()
