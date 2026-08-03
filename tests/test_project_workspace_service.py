from __future__ import annotations

import unittest
from datetime import date, datetime, time, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import Event, Project, User
from app.services import project_workspace_service
from app.services.project_workspace_service import WorkspaceError
from app.utils.constants import ApplicationStatus, EventStatus, ProjectStatus, Role


class ProjectWorkspaceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(
            bot_token="1234567890:test-token",
            miniapp_auth_secret="secret",
        )

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int, first_name: str, **overrides) -> User:
        defaults = dict(
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
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    def _project(self, *, author_id: int, **overrides) -> Project:
        defaults = dict(
            author_id=author_id,
            title="Media Lab",
            short_description="Project for media growth",
            status=ProjectStatus.APPROVED,
        )
        defaults.update(overrides)
        return Project(**defaults)

    async def test_role_application_approval_and_capacity(self) -> None:
        async with self.session_factory() as session:
            author = await self._make_user(session, 1, "Leader")
            applicant = await self._make_user(session, 2, "Meri")
            second = await self._make_user(session, 3, "Aram")
            project = self._project(author_id=author.id)
            session.add(project)
            await session.flush()

            role = await project_workspace_service.create_role(
                session,
                project,
                author,
                title="SMM-координатор",
                capacity=1,
            )
            with self.assertRaises(WorkspaceError) as duplicate_ctx:
                await project_workspace_service.create_role(
                    session,
                    project,
                    author,
                    title="SMM-координатор",
                )
            self.assertEqual(duplicate_ctx.exception.code, "role_already_exists")
            pending = await project_workspace_service.apply_to_role(
                session,
                project,
                applicant,
                role_id=role.id,
                application_text="Хочу вести медиа проекта",
            )
            accepted = await project_workspace_service.review_application(
                session, project, author, pending.id, approve=True
            )

            self.assertEqual(accepted.status, "accepted")
            self.assertEqual(accepted.approved_by, author.id)
            self.assertIsNotNone(accepted.joined_at)

            with self.assertRaises(WorkspaceError) as ctx:
                await project_workspace_service.apply_to_role(
                    session,
                    project,
                    second,
                    role_id=role.id,
                    application_text="Тоже хочу в команду",
                )

            self.assertEqual(ctx.exception.code, "role_full")
            snapshot = await project_workspace_service.workspace_snapshot(
                session, project, author, self.settings
            )
            self.assertEqual(snapshot.roles[0].filled, 1)

    async def test_workspace_permissions_are_backend_enforced(self) -> None:
        async with self.session_factory() as session:
            author = await self._make_user(session, 1, "Leader")
            stranger = await self._make_user(session, 2, "Guest")
            admin = await self._make_user(session, 3, "Admin", role=Role.ADMIN)
            draft = self._project(author_id=author.id, status=ProjectStatus.DRAFT)
            session.add(draft)
            await session.flush()

            with self.assertRaises(WorkspaceError) as view_ctx:
                await project_workspace_service.require_project(
                    session, draft.id, stranger, self.settings
                )
            self.assertEqual(view_ctx.exception.code, "project_not_found")

            with self.assertRaises(WorkspaceError) as manage_ctx:
                await project_workspace_service.require_project(
                    session, draft.id, stranger, self.settings, manage=True
                )
            self.assertEqual(manage_ctx.exception.code, "not_allowed")

            managed = await project_workspace_service.require_project(
                session, draft.id, admin, self.settings, manage=True
            )
            self.assertEqual(managed.id, draft.id)

    async def test_milestone_task_event_and_contribution_flow(self) -> None:
        async with self.session_factory() as session:
            author = await self._make_user(session, 1, "Leader")
            member_user = await self._make_user(session, 2, "Meri")
            project = self._project(author_id=author.id)
            session.add(project)
            await session.flush()

            role = await project_workspace_service.create_role(
                session, project, author, title="Медиа"
            )
            member = await project_workspace_service.add_member(
                session,
                project,
                author,
                user_id=member_user.id,
                role_id=role.id,
            )
            milestone = await project_workspace_service.create_milestone(
                session,
                project,
                author,
                title="Подготовка",
                deadline=datetime(2026, 8, 10, 18, 0, tzinfo=timezone.utc),
                responsible_id=member_user.id,
            )
            completed = await project_workspace_service.set_milestone_status(
                session,
                project,
                author,
                milestone.id,
                status="completed",
            )
            task = await project_workspace_service.create_project_task(
                session,
                project,
                author,
                title="Подготовить пять публикаций",
                description="Собрать контент-план и тексты",
                deadline=datetime(2026, 8, 9, 18, 0, tzinfo=timezone.utc),
                assignee_id=member_user.id,
                points=15,
            )
            event = Event(
                title="Презентация проекта",
                description="Открытая встреча",
                event_date=date(2026, 8, 12),
                event_time=time(18, 0),
                location="Дом Москвы",
                format="offline",
                created_by=author.id,
                status=EventStatus.APPROVED,
            )
            session.add(event)
            await session.flush()
            linked = await project_workspace_service.link_event(
                session, project, author, event.id
            )
            confirmed = await project_workspace_service.confirm_contribution(
                session,
                project,
                author,
                member.id,
                summary="Подготовила медиаплан и публикации",
                result="5 публикаций",
            )

            self.assertEqual(completed.completed_by, author.id)
            self.assertEqual(task.project_id, project.id)
            self.assertEqual(task.assignee_id, member_user.id)
            self.assertEqual(linked.project_id, project.id)
            self.assertEqual(confirmed.contribution_status, "confirmed")
            self.assertEqual(confirmed.contribution_confirmed_by, author.id)
            self.assertEqual(confirmed.contribution_role_title, "Медиа")

    async def test_project_author_can_assign_self_without_member_row(self) -> None:
        async with self.session_factory() as session:
            author = await self._make_user(session, 1, "Leader")
            project = self._project(author_id=author.id)
            session.add(project)
            await session.flush()

            task = await project_workspace_service.create_project_task(
                session,
                project,
                author,
                title="Собрать команду",
                description="Открыть роли и пригласить участников",
                deadline=datetime(2026, 8, 9, 18, 0, tzinfo=timezone.utc),
                assignee_id=author.id,
            )

            self.assertEqual(task.assignee_id, author.id)


if __name__ == "__main__":
    unittest.main()
