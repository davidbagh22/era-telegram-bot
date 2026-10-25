from __future__ import annotations

import unittest
from datetime import datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Project, ProjectMember, ProjectMilestone, User
from app.services.activity_metrics_service import get_metric
from app.services.points_service import total_points
from app.services.project_scoring_reconciliation_service import reconcile_project_scoring


class ProjectScoringReconciliationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_confirmed_project_facts_are_scored_once(self) -> None:
        async with self.session_factory() as session:
            lead = User(telegram_id=1, first_name="Lead")
            member_user = User(telegram_id=2, first_name="Member")
            session.add_all([lead, member_user])
            await session.flush()
            project = Project(
                author_id=lead.id,
                title="Project",
                short_description="d",
                status="completed",
            )
            session.add(project)
            await session.flush()
            member = ProjectMember(
                project_id=project.id,
                user_id=member_user.id,
                status="accepted",
                contribution_status="confirmed",
                contribution_summary="Result",
                contribution_confirmed_at=datetime.now().astimezone(),
                contribution_confirmed_by=lead.id,
            )
            milestone = ProjectMilestone(
                project_id=project.id,
                title="M1",
                sort_order=1,
                responsible_id=member_user.id,
                status="completed",
                completed_at=datetime.now().astimezone(),
                completed_by=lead.id,
            )
            session.add_all([member, milestone])
            await session.flush()

            await reconcile_project_scoring(session)
            member_points = await total_points(session, member_user.id)
            lead_points = await total_points(session, lead.id)
            await reconcile_project_scoring(session)

            # Member: first confirmed contribution 50 + milestone 120 +
            # completed-project participant reward 250.
            self.assertEqual(member_points, 420)
            self.assertEqual(await total_points(session, member_user.id), 420)

            # Authorship alone is not a verified contribution. The project
            # author receives neither participant-completion nor lead-result
            # points until their own ProjectMember contribution is confirmed.
            self.assertEqual(lead_points, 0)
            self.assertEqual(await total_points(session, lead.id), 0)
            self.assertEqual(
                await get_metric(
                    session, user_id=member_user.id, metric_key="projects_completed"
                ),
                1,
            )
            self.assertEqual(
                await get_metric(session, user_id=lead.id, metric_key="projects_led"),
                0,
            )

    async def test_confirmed_project_lead_receives_lead_result_once(self) -> None:
        async with self.session_factory() as session:
            lead = User(telegram_id=11, first_name="Lead")
            session.add(lead)
            await session.flush()
            project = Project(
                author_id=lead.id,
                title="Led project",
                short_description="d",
                status="completed",
            )
            session.add(project)
            await session.flush()
            session.add(
                ProjectMember(
                    project_id=project.id,
                    user_id=lead.id,
                    status="accepted",
                    contribution_status="confirmed",
                    contribution_summary="Led delivery",
                    contribution_confirmed_at=datetime.now().astimezone(),
                    contribution_confirmed_by=lead.id,
                )
            )
            await session.flush()

            await reconcile_project_scoring(session)
            first_total = await total_points(session, lead.id)
            await reconcile_project_scoring(session)

            # 50 first contribution + 250 completed project + 150 Project Lead result.
            self.assertEqual(first_total, 450)
            self.assertEqual(await total_points(session, lead.id), 450)
            self.assertEqual(
                await get_metric(session, user_id=lead.id, metric_key="projects_led"),
                1,
            )


if __name__ == "__main__":
    unittest.main()
