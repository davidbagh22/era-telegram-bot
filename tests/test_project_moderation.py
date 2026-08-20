from __future__ import annotations

import unittest

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import PointTransaction, PortfolioItem, Project, User
from app.services import project_workflow_service
from app.utils.constants import ProjectStatus


def _points_sum_query(user_id: int):
    return select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
        PointTransaction.user_id == user_id
    )


def _portfolio_query(user_id: int):
    return select(PortfolioItem).where(PortfolioItem.user_id == user_id)


class ProjectModerationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int = 1, **overrides) -> User:
        defaults = dict(
            telegram_id=telegram_id,
            first_name="Dev",
            last_name=None,
            phone="+10000000000",
            city="City",
            education_work="Work",
            occupation="Occupation",
            motivation="Motivation",
            available_time="Evenings",
            desired_path="participant",
            personal_data_consent=True,
            is_channel_subscribed=True,
        )
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    def _project(self, *, author_id: int, **overrides) -> Project:
        defaults = dict(
            title="Idea", short_description="d", status=ProjectStatus.INITIAL_REVIEW
        )
        defaults.update(overrides)
        return Project(author_id=author_id, **defaults)

    async def test_initial_accept_moves_to_venue_review(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1)
            author = await self._make_user(session, telegram_id=2)
            project = self._project(author_id=author.id)
            session.add(project)
            await session.flush()

            result = await project_workflow_service.decide_project(
                session, project, action="initial_accept", comment="ok", actor=admin
            )
            self.assertEqual(project.status, ProjectStatus.VENUE_REVIEW)
            self.assertEqual(project.venue_status, "pending")
            self.assertIn("следующему этапу", result.notice)

    async def test_venue_approve_does_not_award_unverified_result(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1)
            author = await self._make_user(session, telegram_id=2)
            project = self._project(author_id=author.id, status=ProjectStatus.VENUE_REVIEW)
            session.add(project)
            await session.flush()

            await project_workflow_service.decide_project(
                session, project, action="venue_approve", comment="ok", actor=admin
            )
            self.assertEqual(project.status, ProjectStatus.APPROVED)

            # Approval only authorizes the project to start. It is not a
            # verified contribution/result and therefore must create neither
            # reputation points nor a verified portfolio achievement.
            points = await session.scalar(_points_sum_query(author.id))
            self.assertEqual(points, 0)
            portfolio_count = len((await session.scalars(_portfolio_query(author.id))).all())
            self.assertEqual(portfolio_count, 0)

            # Re-approving remains idempotent and still creates no reward.
            await project_workflow_service.decide_project(
                session, project, action="venue_approve", comment="again", actor=admin
            )
            points_after = await session.scalar(_points_sum_query(author.id))
            self.assertEqual(points_after, 0)
            portfolio_count_after = len((await session.scalars(_portfolio_query(author.id))).all())
            self.assertEqual(portfolio_count_after, 0)

    async def test_revise_postpone_reject(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1)
            author = await self._make_user(session, telegram_id=2)

            for action, expected in (
                ("revise", ProjectStatus.NEEDS_REVISION),
                ("postpone", ProjectStatus.POSTPONED),
                ("reject", ProjectStatus.REJECTED),
            ):
                project = self._project(author_id=author.id)
                session.add(project)
                await session.flush()
                await project_workflow_service.decide_project(
                    session, project, action=action, comment="x", actor=admin
                )
                self.assertEqual(project.status, expected)

    async def test_unknown_action_raises(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1)
            author = await self._make_user(session, telegram_id=2)
            project = self._project(author_id=author.id)
            session.add(project)
            await session.flush()

            with self.assertRaises(ValueError):
                await project_workflow_service.decide_project(
                    session, project, action="not_a_real_action", comment="x", actor=admin
                )

    async def test_list_projects_for_review_only_review_statuses(self) -> None:
        async with self.session_factory() as session:
            author = await self._make_user(session, telegram_id=1)
            in_review = self._project(author_id=author.id, status=ProjectStatus.PENDING_REVIEW)
            approved = self._project(author_id=author.id, status=ProjectStatus.APPROVED)
            session.add_all([in_review, approved])
            await session.flush()

            rows = await project_workflow_service.list_projects_for_review(session)
            self.assertEqual([p.id for p in rows], [in_review.id])


if __name__ == "__main__":
    unittest.main()
