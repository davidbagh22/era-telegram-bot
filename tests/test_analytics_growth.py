import unittest
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AuditLog, Event, EventRegistration, PointTransaction, Task, TaskSubmission, User
from app.services.analytics_growth_service import build_growth_snapshot


class GrowthTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_observed_ordered_transitions_and_distinct_results_count(self):
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        at = lambda days: now - timedelta(days=days)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            people = [User(telegram_id=i, first_name=f'U{i}', role='leader',
                           application_status='approved', created_at=at(80)) for i in (1, 2, 3)]
            old = User(telegram_id=4, first_name='Outside cohort', created_at=at(91))
            session.add_all([*people, old]); await session.flush()
            event = Event(title='One event', description='fixture', event_date=date(2026, 8, 21), event_time=time(12), location='online', format='online', created_by=people[0].id)
            task = Task(title='Second result', description='fixture', creator_id=people[0].id)
            session.add_all([event, task]); await session.flush()
            submission = TaskSubmission(task_id=task.id, user_id=people[0].id, status='approved')
            session.add(submission); await session.flush()
            for user in (people[0], people[2]):
                session.add(AuditLog(action='user.approved', entity_type='user', entity_id=user.id, created_at=at(70)))
            session.add(EventRegistration(event_id=event.id, user_id=people[0].id, status='attended', last_confirmation_at=at(60)))
            for source in ('event_attendance', 'event_scoring_role', 'event_scoring_volunteer'):
                session.add(PointTransaction(user_id=people[0].id, points=5, reason='same event', source_type=source, related_event_id=event.id, created_at=at(60)))
            session.add(PointTransaction(user_id=people[2].id, points=100, reason='digital only', source_type='digital_engagement', created_at=at(60)))
            session.add(AuditLog(action='task.submission_approve', entity_type='task_submission', entity_id=submission.id, created_at=at(50)))
            for role, days in [('activist', 40), ('leader', 30)]:
                session.add(AuditLog(action='user.role_changed', entity_type='user', entity_id=people[0].id, new_value={'role': role}, created_at=at(days)))
            await session.commit()
            growth = await build_growth_snapshot(session, now=now)
            assert [stage.count for stage in growth.stages] == [3, 2, 1, 1, 1, 1]
            assert growth.stages[3].median_days == 10
            assert growth.stages[3].conversion == 100
            assert growth.stages[2].lost_user_ids == (people[2].id,)
            assert growth.approval_history_missing == 1
        await engine.dispose()

    async def test_empty_cohort_returns_unknown_conversions(self):
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine)() as session:
            growth = await build_growth_snapshot(session)
            assert all(stage.count == 0 and stage.conversion is None for stage in growth.stages)
        await engine.dispose()
