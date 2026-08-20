from __future__ import annotations

import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Project, ProjectMember, User
from app.services.activity_scoring_service import score_project_completion
from app.services.points_service import total_points


class ProjectVerifiedRewardsRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _user(self, session, telegram_id: int) -> User:
        user = User(telegram_id=telegram_id, first_name=f"U{telegram_id}")
        session.add(user)
        await session.flush()
        return user

    async def test_author_without_confirmed_contribution_gets_no_completion_reward(self) -> None:
        async with self.session_factory() as session:
            author = await self._user(session, 1)
            project = Project(
                author_id=author.id,
                title="Verified project",
                short_description="Result must be verified",
            )
            session.add(project)
            await session.flush()

            awarded = await score_project_completion(
                session, project, approved_by_id=author.id
            )

            self.assertEqual(awarded, [])
            self.assertEqual(await total_points(session, author.id), 0)

    async def test_confirmed_author_gets_completion_and_lead_result_once(self) -> None:
        async with self.session_factory() as session:
            author = await self._user(session, 10)
            project = Project(
                author_id=author.id,
                title="Verified lead project",
                short_description="Confirmed result",
            )
            session.add(project)
            await session.flush()
            session.add(
                ProjectMember(
                    project_id=project.id,
                    user_id=author.id,
                    status="completed",
                    contribution_status="confirmed",
                    contribution_summary="Led delivery and confirmed the result",
                )
            )
            await session.flush()

            first = await score_project_completion(
                session, project, approved_by_id=author.id
            )
            second = await score_project_completion(
                session, project, approved_by_id=author.id
            )

            self.assertEqual(len(first), 2)
            self.assertEqual(len(second), 2)
            # 250 completed-project participant + 150 verified Project Lead result.
            self.assertEqual(await total_points(session, author.id), 400)


if __name__ == "__main__":
    unittest.main()
