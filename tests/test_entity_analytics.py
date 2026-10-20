import unittest
from datetime import datetime, time, timedelta, timezone
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Event, EventRegistration, Feedback, Project, ProjectMember, ProjectMilestone, User
from app.services.analytics_snapshot_service import build_event_analytics, build_project_analytics, delivery_problem_counts
from app.services.excel_service import build_analytics_workbook


class EntityAnalyticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_attendance_denominator_feedback_and_project_results(self):
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            users = [User(telegram_id=i, first_name=f'U{i}', application_status='approved') for i in range(1,7)]
            session.add_all(users); await session.flush()
            current = Event(title='Current', description='Fixture', event_date=(now-timedelta(days=10)).date(), event_time=time(12),
                            location='Online', format='online', created_by=users[0].id, status='completed')
            old = Event(title='Old', description='Fixture', event_date=(now-timedelta(days=40)).date(), event_time=time(12),
                        location='Online', format='online', created_by=users[0].id, status='completed')
            project = Project(title='Active', short_description='Fixture', author_id=users[0].id, status='in_progress')
            cancelled = Project(title='Cancelled', short_description='Fixture', author_id=users[0].id, status='cancelled')
            stalled = Project(title='Needs follow-up', short_description='Fixture', author_id=users[0].id, status='in_progress', created_at=now-timedelta(days=40))
            session.add_all([current, old, project, cancelled, stalled]); await session.flush()
            for person, status in zip(users, ['attended', 'attended', 'registered', 'no_show', 'waitlist', 'cancelled']):
                session.add(EventRegistration(user_id=person.id, event_id=current.id, status=status))
            session.add(EventRegistration(user_id=users[0].id, event_id=old.id, status='attended'))
            session.add(Feedback(user_id=users[0].id, event_id=current.id, rating=4, liked='Fixture', improve='Fixture', wants_again='yes'))
            session.add(ProjectMember(user_id=users[0].id, project_id=project.id, status='accepted', contribution_status='confirmed', contribution_confirmed_at=now-timedelta(days=3)))
            session.add(ProjectMember(user_id=users[1].id, project_id=project.id, status='pending'))
            session.add_all([
                ProjectMilestone(project_id=project.id, title='Late', sort_order=1, status='pending', deadline=now-timedelta(days=2)),
                ProjectMilestone(project_id=project.id, title='Done', sort_order=2, status='completed', completed_at=now-timedelta(days=3), deadline=now-timedelta(days=5)),
                ProjectMilestone(project_id=cancelled.id, title='Cancelled project', status='pending', deadline=now-timedelta(days=5)),
            ])
            await session.commit()
            events = await build_event_analytics(session, now=now)
            metrics = {m.key: m for m in events.metrics}
            assert metrics['held'].value == 1 and metrics['held'].previous == 1
            assert metrics['registrations'].value == 4
            assert metrics['attended'].value == 2
            assert metrics['attendance'].value == 50
            assert metrics['first'].value == 1 and metrics['returning'].value == 1
            assert metrics['ratings'].value == 1 and metrics['average'].value == 4
            empty_week = await build_event_analytics(session, days=7, now=now)
            assert next(m for m in empty_week.metrics if m.key == 'attendance').value is None
            assert next(m for m in empty_week.metrics if m.key == 'average').value is None
            projects = await build_project_analytics(session, now=now)
            metrics = {m.key: m for m in projects.metrics}
            assert metrics['active'].value == 2 and metrics['active'].previous is None
            assert metrics['participants'].value == 1
            assert metrics['contributions'].value == 1
            assert metrics['milestones'].value == 1
            assert metrics['overdue'].value == 1
            assert metrics['without_results'].value == 1
            workbook = load_workbook(BytesIO(build_analytics_workbook([], [], [], {}, entity_snapshots=[('События 2.0', events), ('Проекты 2.0', projects)])))
            assert [row[1] for row in list(workbook['События 2.0'].values)[1:]] == [m.value for m in events.metrics]
            assert [row[1] for row in list(workbook['Проекты 2.0'].values)[1:]] == [m.value for m in projects.metrics]
        await engine.dispose()


    async def test_delivery_warnings_clear_when_the_same_receipt_is_sent(self):
        from app.database.system_models import NotificationDelivery
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        now = datetime.now(timezone.utc)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            report = NotificationDelivery(delivery_key='fixture-report', chat_id=1, notification_type='management_report', status='failed', payload_hash='fixture', last_attempt_at=now-timedelta(hours=1))
            campaign = NotificationDelivery(delivery_key='fixture-campaign', chat_id=1, notification_type='leaders_broadcast', status='uncertain', payload_hash='fixture', last_attempt_at=now-timedelta(hours=1))
            session.add_all([report, campaign]); await session.commit()
            assert await delivery_problem_counts(session, now=now) == {'reports': 1, 'broadcasts': 1}
            report.status = 'sent'; await session.commit()
            assert await delivery_problem_counts(session, now=now) == {'reports': 0, 'broadcasts': 1}
        await engine.dispose()
