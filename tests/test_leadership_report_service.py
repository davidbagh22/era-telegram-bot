from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import LeadershipGoal, Office, Task, User, UserOffice
from app.services import leadership_report_service as svc
from app.utils.constants import (
    AttentionItemStatus,
    LeadershipReportStatus,
    TaskStatus,
)


class LeadershipReportServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int) -> User:
        user = User(telegram_id=telegram_id, first_name=f"U{telegram_id}")
        session.add(user)
        await session.flush()
        return user

    async def test_submit_green_report_no_escalation(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, 1)
            result = await svc.submit_quick_report(
                session,
                owner_id=user.id,
                period_start=date.today(),
                period_end=date.today() + timedelta(days=6),
                status=LeadershipReportStatus.ON_TRACK,
                main_result="Всё по плану",
            )
            self.assertIsNone(result.attention_item)
            self.assertEqual(result.report.status, "green")

    async def test_submit_report_is_idempotent_per_period(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, 1)
            period_start = date.today()
            first = await svc.submit_quick_report(
                session,
                owner_id=user.id,
                period_start=period_start,
                period_end=period_start + timedelta(days=6),
                status=LeadershipReportStatus.ON_TRACK,
            )
            second = await svc.submit_quick_report(
                session,
                owner_id=user.id,
                period_start=period_start,
                period_end=period_start + timedelta(days=6),
                status=LeadershipReportStatus.AT_RISK,
            )
            self.assertEqual(first.report.id, second.report.id)
            reports = await svc.list_reports(session, owner_id=user.id)
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0].status, "yellow")

    async def test_red_status_creates_attention_item_and_notifies_admin(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, 1)
            result = await svc.submit_quick_report(
                session,
                owner_id=user.id,
                period_start=date.today(),
                period_end=date.today() + timedelta(days=6),
                status=LeadershipReportStatus.NEEDS_HELP,
                blocker_type="resources",
                blocker_note="Нет площадки",
            )
            self.assertIsNotNone(result.attention_item)
            self.assertEqual(result.attention_item.status, AttentionItemStatus.OPEN)
            self.assertEqual(result.attention_item.owner_id, user.id)

    async def test_repeated_blocker_reuses_existing_open_item(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, 1)
            first = await svc.submit_quick_report(
                session,
                owner_id=user.id,
                period_start=date.today(),
                period_end=date.today() + timedelta(days=6),
                status=LeadershipReportStatus.NEEDS_HELP,
                blocker_note="Первая проблема",
            )
            second = await svc.submit_quick_report(
                session,
                owner_id=user.id,
                period_start=date.today() + timedelta(days=7),
                period_end=date.today() + timedelta(days=13),
                status=LeadershipReportStatus.NEEDS_HELP,
                blocker_note="Вторая проблема",
            )
            self.assertEqual(first.attention_item.id, second.attention_item.id)

    async def test_escalation_target_resolves_via_reports_to_office(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            chief = await self._make_user(session, 2)
            leader = await self._make_user(session, 3)
            parent_office = Office(title="Руководитель направления")
            session.add(parent_office)
            await session.flush()
            child_office = Office(title="Лидер клуба", reports_to_office_id=parent_office.id)
            session.add(child_office)
            await session.flush()
            session.add(UserOffice(office_id=parent_office.id, user_id=chief.id, appointed_by=admin.id))
            assignment = UserOffice(office_id=child_office.id, user_id=leader.id, appointed_by=admin.id)
            session.add(assignment)
            await session.flush()

            target = await svc.resolve_escalation_target(session, assignment)
            self.assertEqual(target.id, chief.id)

    async def test_resolve_attention_item(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, 1)
            result = await svc.submit_quick_report(
                session,
                owner_id=user.id,
                period_start=date.today(),
                period_end=date.today() + timedelta(days=6),
                status=LeadershipReportStatus.NEEDS_HELP,
            )
            await svc.resolve_attention_item(
                session, result.attention_item, resolver_id=user.id, resolution="Помогли"
            )
            self.assertEqual(result.attention_item.status, AttentionItemStatus.RESOLVED)
            self.assertIsNotNone(result.attention_item.resolved_at)

    async def test_run_attention_rules_detects_overdue_tasks(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            leader = await self._make_user(session, 2)
            office = Office(title="Лидер", permission_template=["tasks.manage"])
            session.add(office)
            await session.flush()
            session.add(UserOffice(office_id=office.id, user_id=leader.id, appointed_by=admin.id))
            for i in range(5):
                session.add(
                    Task(
                        title=f"T{i}",
                        description="d",
                        assignee_id=leader.id,
                        creator_id=admin.id,
                        deadline=datetime.now(timezone.utc) - timedelta(days=1),
                        status=TaskStatus.NEW,
                    )
                )
            await session.flush()

            created = await svc.run_attention_rules(session)
            types = {item.type for item in created}
            self.assertIn("leader_overdue_tasks", types)

    async def test_run_attention_rules_detects_no_monthly_goals(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            leader = await self._make_user(session, 2)
            office = Office(title="Лидер", permission_template=["tasks.manage"])
            session.add(office)
            await session.flush()
            session.add(UserOffice(office_id=office.id, user_id=leader.id, appointed_by=admin.id))
            await session.flush()

            created = await svc.run_attention_rules(session)
            types = {item.type for item in created}
            self.assertIn("leader_no_monthly_goals", types)

    async def test_run_attention_rules_skips_when_goal_exists(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            leader = await self._make_user(session, 2)
            office = Office(title="Лидер", permission_template=["tasks.manage"])
            session.add(office)
            await session.flush()
            session.add(UserOffice(office_id=office.id, user_id=leader.id, appointed_by=admin.id))
            session.add(
                LeadershipGoal(
                    owner_id=leader.id,
                    created_by=admin.id,
                    title="Цель месяца",
                    period_start=date.today().replace(day=1),
                    period_end=date.today(),
                )
            )
            await session.flush()

            created = await svc.run_attention_rules(session)
            types = {item.type for item in created}
            self.assertNotIn("leader_no_monthly_goals", types)

    async def test_run_attention_rules_is_deduplicated(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            leader = await self._make_user(session, 2)
            office = Office(title="Лидер", permission_template=["tasks.manage"])
            session.add(office)
            await session.flush()
            session.add(UserOffice(office_id=office.id, user_id=leader.id, appointed_by=admin.id))
            await session.flush()

            first_run = await svc.run_attention_rules(session)
            second_run = await svc.run_attention_rules(session)
            self.assertTrue(len(first_run) > 0)
            self.assertEqual(second_run, [])


if __name__ == "__main__":
    unittest.main()
