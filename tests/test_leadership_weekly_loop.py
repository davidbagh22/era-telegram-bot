from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.leadership_models import LeadershipFeedback, LeadershipReportPulse
from app.database.models import (
    LeadershipAttentionItem,
    Office,
    Task,
    User,
    UserOffice,
)
from app.services import leadership_weekly_service
from app.utils.constants import ApplicationStatus, Role


class LeadershipWeeklyLoopTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

        async with self.factory() as session:
            self.admin = User(
                telegram_id=1001,
                first_name="Admin",
                role=Role.ADMIN,
                application_status=ApplicationStatus.APPROVED,
            )
            self.leader = User(
                telegram_id=1002,
                first_name="Leader",
                role=Role.LEADER,
                application_status=ApplicationStatus.APPROVED,
            )
            session.add_all([self.admin, self.leader])
            await session.flush()
            self.office = Office(
                title="Test Leader Office",
                scope_type="global",
                permission_template=["people.view"],
                is_active=True,
            )
            session.add(self.office)
            await session.flush()
            self.assignment = UserOffice(
                user_id=self.leader.id,
                office_id=self.office.id,
                appointed_by=self.admin.id,
                starts_at=date.today() - timedelta(days=30),
                is_active=True,
            )
            session.add(self.assignment)
            await session.commit()
            self.admin_id = self.admin.id
            self.leader_id = self.leader.id
            self.assignment_id = self.assignment.id

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_weekly_report_is_prefilled_with_immutable_system_facts(self) -> None:
        week_start, _ = leadership_weekly_service.week_bounds()
        async with self.factory() as session:
            view = await leadership_weekly_service.ensure_weekly_report(
                session,
                owner_id=self.leader_id,
                period_start=week_start,
                office_assignment_id=self.assignment_id,
            )
            snapshot = dict(view.pulse.system_snapshot)
            self.assertEqual(snapshot["period_start"], week_start.isoformat())
            self.assertEqual(snapshot["scope_type"], "global")
            self.assertIn("tasks_overdue", snapshot)
            self.assertIn("projects_active", snapshot)
            self.assertIsNone(view.report.submitted_at)

            # A later open returns the same persisted facts rather than accepting
            # client-supplied replacements/recomputing historical data in place.
            view.pulse.system_snapshot["sentinel"] = "server-owned"
            await session.commit()
            reopened = await leadership_weekly_service.ensure_weekly_report(
                session,
                owner_id=self.leader_id,
                period_start=week_start,
            )
            self.assertEqual(reopened.pulse.system_snapshot["sentinel"], "server-owned")

    async def test_submit_updates_subjective_fields_but_not_system_snapshot(self) -> None:
        week_start, _ = leadership_weekly_service.week_bounds()
        async with self.factory() as session:
            view = await leadership_weekly_service.ensure_weekly_report(
                session,
                owner_id=self.leader_id,
                period_start=week_start,
                office_assignment_id=self.assignment_id,
            )
            original = dict(view.pulse.system_snapshot)
            submitted = await leadership_weekly_service.submit_weekly_pulse(
                session,
                owner_id=self.leader_id,
                period_start=week_start,
                status="green",
                office_assignment_id=self.assignment_id,
                main_result="Закрыли ключевую задачу",
                pace_score=4,
                clarity_score=5,
                load_score=3,
                attention_text="Нужна синхронизация по следующей неделе",
            )
            self.assertEqual(submitted.pulse.system_snapshot, original)
            self.assertEqual(submitted.pulse.pace_score, 4)
            self.assertEqual(submitted.pulse.clarity_score, 5)
            self.assertEqual(submitted.pulse.load_score, 3)
            self.assertIsNotNone(submitted.report.submitted_at)

    async def test_feedback_history_is_persisted_and_scoped(self) -> None:
        week_start, _ = leadership_weekly_service.week_bounds()
        async with self.factory() as session:
            view = await leadership_weekly_service.ensure_weekly_report(
                session,
                owner_id=self.leader_id,
                period_start=week_start,
                office_assignment_id=self.assignment_id,
            )
            admin = await session.get(User, self.admin_id)
            first = await leadership_weekly_service.add_feedback(
                session,
                report=view.report,
                reviewer=admin,
                status="acknowledged",
                comment="Принято",
            )
            second = await leadership_weekly_service.add_feedback(
                session,
                report=view.report,
                reviewer=admin,
                status="follow_up",
                comment="Нужен следующий шаг",
            )
            await session.commit()
            history = await leadership_weekly_service.list_feedback(
                session, report_id=view.report.id
            )
            self.assertEqual([item.id for item in history], [first.id, second.id])
            self.assertEqual(
                len((await session.scalars(select(LeadershipFeedback))).all()), 2
            )

    async def test_missed_report_signal_is_idempotent(self) -> None:
        week_start, _ = leadership_weekly_service.week_bounds()
        async with self.factory() as session:
            first = await leadership_weekly_service.run_missed_report_signals(
                session, period_start=week_start
            )
            await session.commit()
            second = await leadership_weekly_service.run_missed_report_signals(
                session, period_start=week_start
            )
            await session.commit()
            self.assertEqual(len(first), 1)
            self.assertEqual(second, [])
            rows = (
                await session.scalars(
                    select(LeadershipAttentionItem).where(
                        LeadershipAttentionItem.type
                        == leadership_weekly_service.MISSED_REPORT_TYPE
                    )
                )
            ).all()
            self.assertEqual(len(rows), 1)

    async def test_objective_subjective_divergence_creates_attention_signal(self) -> None:
        week_start, _ = leadership_weekly_service.week_bounds()
        now = datetime.now(timezone.utc)
        async with self.factory() as session:
            # Two objective overdue tasks make the system snapshot risky.
            session.add_all(
                [
                    Task(
                        title=f"Overdue {index}",
                        description="test",
                        assignee_id=self.leader_id,
                        creator_id=self.admin_id,
                        deadline=now - timedelta(days=index + 1),
                        points=40,
                        status="in_progress",
                    )
                    for index in range(2)
                ]
            )
            await session.flush()
            view = await leadership_weekly_service.submit_weekly_pulse(
                session,
                owner_id=self.leader_id,
                period_start=week_start,
                status="green",
                office_assignment_id=self.assignment_id,
                pace_score=5,
                clarity_score=5,
                load_score=2,
            )
            await session.commit()
            self.assertGreaterEqual(view.pulse.system_snapshot["tasks_overdue"], 2)
            signal = await session.scalar(
                select(LeadershipAttentionItem).where(
                    LeadershipAttentionItem.type
                    == leadership_weekly_service.DIVERGENCE_TYPE,
                    LeadershipAttentionItem.owner_id == self.leader_id,
                )
            )
            self.assertIsNotNone(signal)

    async def test_snapshot_scope_does_not_accept_client_scope_override(self) -> None:
        week_start, _ = leadership_weekly_service.week_bounds()
        async with self.factory() as session:
            view = await leadership_weekly_service.submit_weekly_pulse(
                session,
                owner_id=self.leader_id,
                period_start=week_start,
                status="yellow",
                office_assignment_id=self.assignment_id,
                pace_score=3,
                clarity_score=3,
                load_score=4,
            )
            self.assertEqual(view.report.scope_type, "global")
            pulse = await session.scalar(
                select(LeadershipReportPulse).where(
                    LeadershipReportPulse.report_id == view.report.id
                )
            )
            self.assertEqual(pulse.system_snapshot["scope_type"], "global")


if __name__ == "__main__":
    unittest.main()
