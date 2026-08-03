from __future__ import annotations

import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Project, User
from app.services import project_workflow_service
from app.utils.constants import ProjectStatus


class ProjectWorkflowServiceTests(unittest.IsolatedAsyncioTestCase):
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
            author_id=author_id,
            title="Idea",
            short_description="d",
            status=ProjectStatus.DRAFT,
        )
        defaults.update(overrides)
        return Project(**defaults)

    async def test_create_draft_uses_idea_as_title_and_description(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            project = await project_workflow_service.create_draft(
                session, user, "Мы делаем квест для новичков"
            )
            self.assertEqual(project.title, "Мы делаем квест для новичков")
            self.assertEqual(project.short_description, "Мы делаем квест для новичков")
            self.assertEqual(project.status, ProjectStatus.DRAFT)
            self.assertEqual(project.form_data, {"idea": "Мы делаем квест для новичков"})

    async def test_create_draft_with_empty_idea_uses_placeholder(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            project = await project_workflow_service.create_draft(session, user, "")
            self.assertEqual(project.title, "Новый проект")
            self.assertEqual(project.form_data, {})

    async def test_update_answers_maps_known_keys_to_columns(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            project = self._project(author_id=user.id)
            session.add(project)
            await session.flush()

            project_workflow_service.update_answers(
                project,
                {
                    "title": "Новое имя",
                    "target_audience": "Студенты 18-22",
                    "unknown_key": "ignored",
                },
            )

            self.assertEqual(project.title, "Новое имя")
            self.assertEqual(project.target_audience, "Студенты 18-22")
            self.assertEqual(project.form_data["title"], "Новое имя")
            self.assertNotIn("unknown_key", project.form_data)

    async def test_can_edit_submit_delete_gates(self) -> None:
        draft = self._project(author_id=1, status=ProjectStatus.DRAFT)
        review = self._project(author_id=1, status=ProjectStatus.INITIAL_REVIEW)
        rejected = self._project(author_id=1, status=ProjectStatus.REJECTED)

        self.assertTrue(project_workflow_service.can_edit(draft))
        self.assertTrue(project_workflow_service.can_submit_for_review(draft))
        self.assertTrue(project_workflow_service.can_delete(draft))

        self.assertFalse(project_workflow_service.can_edit(review))
        self.assertFalse(project_workflow_service.can_submit_for_review(review))
        self.assertFalse(project_workflow_service.can_delete(review))

        self.assertFalse(project_workflow_service.can_edit(rejected))
        self.assertTrue(project_workflow_service.can_delete(rejected))

    async def test_submit_for_review_transitions_status_and_generates_document(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            project = self._project(
                author_id=user.id, form_data={"idea": "Идея", "title": "Название"}
            )
            session.add(project)
            await session.flush()

            document = await project_workflow_service.submit_for_review(session, project, user)

            self.assertEqual(project.status, ProjectStatus.INITIAL_REVIEW)
            self.assertIsNotNone(project.submitted_at)
            self.assertEqual(project.generated_document, document)
            self.assertIn("Название", document)

    async def test_submit_for_review_reuses_existing_document(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            project = self._project(author_id=user.id, generated_document="ALREADY THERE")
            session.add(project)
            await session.flush()

            document = await project_workflow_service.submit_for_review(session, project, user)
            self.assertEqual(document, "ALREADY THERE")

    async def test_cancel_project_sets_cancelled_status(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            project = self._project(author_id=user.id)
            session.add(project)
            await session.flush()

            await project_workflow_service.cancel_project(session, project, user)
            self.assertEqual(project.status, ProjectStatus.CANCELLED)

    async def test_list_scopes(self) -> None:
        async with self.session_factory() as session:
            owner = await self._make_user(session, telegram_id=1)
            other = await self._make_user(session, telegram_id=2)
            draft = self._project(author_id=owner.id, status=ProjectStatus.DRAFT)
            in_review = self._project(author_id=owner.id, status=ProjectStatus.INITIAL_REVIEW)
            completed = self._project(author_id=owner.id, status=ProjectStatus.COMPLETED)
            cancelled = self._project(author_id=owner.id, status=ProjectStatus.CANCELLED)
            others_open = self._project(author_id=other.id, status=ProjectStatus.APPROVED)
            session.add_all([draft, in_review, completed, cancelled, others_open])
            await session.flush()

            mine = await project_workflow_service.list_projects_for_user(session, owner, "mine")
            self.assertEqual(
                {p.id for p in mine}, {draft.id, in_review.id, completed.id}
            )

            proposals = await project_workflow_service.list_projects_for_user(
                session, owner, "proposals"
            )
            self.assertEqual({p.id for p in proposals}, {in_review.id})

            done = await project_workflow_service.list_projects_for_user(
                session, owner, "completed"
            )
            self.assertEqual({p.id for p in done}, {completed.id})

            open_projects = await project_workflow_service.list_projects_for_user(
                session, owner, "open"
            )
            self.assertEqual({p.id for p in open_projects}, {others_open.id})


if __name__ == "__main__":
    unittest.main()
