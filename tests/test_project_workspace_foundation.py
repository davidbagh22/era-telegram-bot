from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Project, ProjectMember, ProjectRole, User
from app.services.portfolio_service import build_portfolio_data
from app.utils.constants import ApplicationStatus, ProjectStatus


class ProjectWorkspaceFoundationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int, first_name: str) -> User:
        user = User(
            telegram_id=telegram_id,
            first_name=first_name,
            last_name=None,
            application_status=ApplicationStatus.APPROVED,
            phone="+10000000000",
            city="Yerevan",
            education_work="ERA",
            occupation="Participant",
            motivation="Grow",
            available_time="Evenings",
            desired_path="leader",
            personal_data_consent=True,
            is_channel_subscribed=True,
        )
        session.add(user)
        await session.flush()
        return user

    async def test_confirmed_project_contribution_enters_portfolio(self) -> None:
        async with self.session_factory() as session:
            author = await self._make_user(session, 1, "Leader")
            contributor = await self._make_user(session, 2, "Meri")
            project = Project(
                author_id=author.id,
                title="Media Lab",
                short_description="Project for media growth",
                status=ProjectStatus.IN_PROGRESS,
            )
            session.add(project)
            await session.flush()
            role = ProjectRole(
                project_id=project.id,
                title="SMM coordinator",
                status="open",
            )
            session.add(role)
            await session.flush()
            session.add_all(
                [
                    ProjectMember(
                        project_id=project.id,
                        user_id=contributor.id,
                        role_id=role.id,
                        status="accepted",
                        joined_at=datetime(2026, 8, 1),
                        contribution_status="confirmed",
                        contribution_summary="Prepared project media plan",
                        contribution_role_title="Media coordinator",
                        contribution_confirmed_at=datetime(2026, 8, 3),
                        contribution_confirmed_by=author.id,
                    ),
                    ProjectMember(
                        project_id=project.id,
                        user_id=author.id,
                        role_id=role.id,
                        status="pending",
                        contribution_status="unconfirmed",
                    ),
                ]
            )
            await session.commit()

            data = await build_portfolio_data(session, contributor)
            project_entries = [entry for entry in data.projects if entry.title == "Media Lab"]

            self.assertEqual(len(project_entries), 1)
            self.assertEqual(project_entries[0].status, "вклад подтверждён")
            self.assertEqual(project_entries[0].category, "Media coordinator")
            self.assertIn("media plan", project_entries[0].description)


def test_project_workspace_schema_can_be_created() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    assert {"project_roles", "project_members", "project_milestones"}.issubset(tables)
    assert "project_id" in {column["name"] for column in inspector.get_columns("tasks")}
    assert "contribution_confirmed_by" in {
        column["name"] for column in inspector.get_columns("project_members")
    }


def test_project_workspace_migration_declares_models_and_task_link() -> None:
    migration = Path("alembic/versions/0012_project_workspace.py").read_text(encoding="utf-8")

    for marker in (
        "project_roles",
        "project_members",
        "project_milestones",
        "fk_tasks_project_id_projects",
        "contribution_confirmed_by",
        "op.add_column(\"tasks\"",
        "bind.dialect.name != \"sqlite\"",
    ):
        assert marker in migration
