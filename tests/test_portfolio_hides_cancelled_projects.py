from __future__ import annotations

import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Project, User
from app.services.portfolio_service import build_portfolio_data
from app.utils.constants import ProjectStatus


class PortfolioCancelledProjectsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_cancelled_and_rejected_authored_projects_are_hidden(self) -> None:
        async with self.session_factory() as session:
            user = User(telegram_id=910001, first_name="Test", last_name="User")
            session.add(user)
            await session.flush()
            session.add_all(
                [
                    Project(
                        author_id=user.id,
                        title="Живой проект",
                        short_description="ok",
                        status=ProjectStatus.IN_PROGRESS,
                    ),
                    Project(
                        author_id=user.id,
                        title="1",
                        short_description="test",
                        status=ProjectStatus.CANCELLED,
                    ),
                    Project(
                        author_id=user.id,
                        title="Отклонённый",
                        short_description="test",
                        status=ProjectStatus.REJECTED,
                    ),
                ]
            )
            await session.commit()

            data = await build_portfolio_data(session, user)
            titles = [entry.title for entry in data.projects]
            self.assertEqual(titles, ["Живой проект"])
