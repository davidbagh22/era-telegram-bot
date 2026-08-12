from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.database.base import Base
from app.database.management_models import MonthlyGoal, OrganizationContact
from app.database.models import ChatGreeting, Department, Direction, User
from app.services.admin_contacts_service import ContactError, archive_contact, create_contact, list_contacts
from app.services.admin_goals_service import GoalError, create_goal, decide_goal, list_goals
from app.services.admin_greetings_service import GreetingError, list_greetings, toggle_greeting, update_greeting_text
from app.services.admin_structure_service import StructureError, list_departments, update_department_description


class _ServiceTestBase(unittest.IsolatedAsyncioTestCase):
    """Real sqlite session — mirrors tests/test_admin_analytics_service.py."""

    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()


class AdminGoalsServiceTests(_ServiceTestBase):
    async def test_create_goal_resolves_department_scope_by_name(self) -> None:
        # ASCII name — SQLite's LOWER() only folds ASCII case (no ICU extension
        # loaded in tests), so a Cyrillic name would make this assertion an
        # artifact of the test DB rather than of the matching logic itself.
        # This is the same func.lower().contains() the bot handler used
        # (app/handlers/admin/management_ready.py) before extraction.
        async with self.session_factory() as session:
            department = Department(name="Media")
            session.add(department)
            await session.commit()

            goal = await create_goal(
                session, title="Провести 2 встречи", target_value=2, month=None,
                scope_query="med", timezone="Europe/Moscow", updated_by=1,
            )
            self.assertEqual(goal.scope_type, "department")
            self.assertEqual(goal.scope_id, department.id)

            goals = await list_goals(session)
            self.assertEqual(len(goals), 1)
            self.assertEqual(goals[0].scope_name, "Media")

    async def test_create_goal_rejects_non_positive_target(self) -> None:
        async with self.session_factory() as session:
            with self.assertRaises(GoalError):
                await create_goal(
                    session, title="X", target_value=0, month=None,
                    scope_query=None, timezone="Europe/Moscow", updated_by=None,
                )

    async def test_decide_goal_inc_done_delete(self) -> None:
        async with self.session_factory() as session:
            goal = MonthlyGoal(month="2026-08", title="Цель", target_value=3, scope_type="global")
            session.add(goal)
            await session.commit()

            updated = await decide_goal(session, goal.id, "inc", updated_by=1)
            self.assertEqual(updated.current_value, 1)

            updated = await decide_goal(session, goal.id, "done", updated_by=1)
            self.assertEqual(updated.status, "done")
            self.assertEqual(updated.current_value, 3)

            updated = await decide_goal(session, goal.id, "delete", updated_by=1)
            self.assertEqual(updated.status, "deleted")
            self.assertEqual([g.id for g in await list_goals(session)], [])

    async def test_decide_goal_missing_raises(self) -> None:
        async with self.session_factory() as session:
            with self.assertRaises(GoalError):
                await decide_goal(session, 999, "inc", updated_by=None)


class AdminContactsServiceTests(_ServiceTestBase):
    async def test_create_and_list_contact(self) -> None:
        async with self.session_factory() as session:
            contact = await create_contact(
                session, organization_name="Партнёр", contact_name="Иван",
                email="i@example.com", created_by=1,
            )
            self.assertEqual(contact.organization_name, "Партнёр")
            listed = await list_contacts(session)
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0].contact_name, "Иван")

    async def test_create_contact_requires_name(self) -> None:
        async with self.session_factory() as session:
            with self.assertRaises(ContactError):
                await create_contact(session, organization_name="   ", created_by=None)

    async def test_archive_contact_hides_from_list(self) -> None:
        async with self.session_factory() as session:
            contact = OrganizationContact(organization_name="Скрыть")
            session.add(contact)
            await session.commit()

            await archive_contact(session, contact.id)
            self.assertEqual(await list_contacts(session), [])

    async def test_archive_missing_contact_raises(self) -> None:
        async with self.session_factory() as session:
            with self.assertRaises(ContactError):
                await archive_contact(session, 999)


class AdminStructureServiceTests(_ServiceTestBase):
    async def test_update_department_description(self) -> None:
        async with self.session_factory() as session:
            department = Department(name="Медиа", description="старое")
            session.add(department)
            await session.commit()

            updated = await update_department_description(session, department.id, "новое описание")
            self.assertEqual(updated.description, "новое описание")
            listed = await list_departments(session)
            self.assertEqual(listed[0].description, "новое описание")

    async def test_update_missing_department_raises(self) -> None:
        async with self.session_factory() as session:
            with self.assertRaises(StructureError):
                await update_department_description(session, 999, "текст")

    async def test_direction_description_not_exposed(self) -> None:
        async with self.session_factory() as session:
            department = Department(name="Медиа")
            session.add(department)
            await session.flush()
            session.add(Direction(name="Соцсети", department_id=department.id, description="direction only"))
            await session.commit()

            listed = await list_departments(session)
            self.assertEqual(len(listed), 1)  # directions are not part of the structure editor's scope


class AdminGreetingsServiceTests(_ServiceTestBase):
    async def test_toggle_and_edit_greeting(self) -> None:
        async with self.session_factory() as session:
            greeting = ChatGreeting(chat_key="general", title="Общий чат", text="Привет, {name}!")
            session.add(greeting)
            await session.commit()

            toggled = await toggle_greeting(session, greeting.id, updated_by=1)
            self.assertFalse(toggled.is_enabled)

            edited = await update_greeting_text(session, greeting.id, "Новый текст", updated_by=1)
            self.assertEqual(edited.text, "Новый текст")

            listed = await list_greetings(session)
            self.assertEqual(listed[0].is_enabled, False)
            self.assertEqual(listed[0].is_bound, False)

    async def test_edit_missing_greeting_raises(self) -> None:
        async with self.session_factory() as session:
            with self.assertRaises(GreetingError):
                await update_greeting_text(session, 999, "текст", updated_by=None)

    async def test_edit_rejects_empty_text(self) -> None:
        async with self.session_factory() as session:
            greeting = ChatGreeting(chat_key="leaders", title="Лидеры", text="Привет")
            session.add(greeting)
            await session.commit()
            with self.assertRaises(GreetingError):
                await update_greeting_text(session, greeting.id, "   ", updated_by=None)


def _admin(**overrides) -> SimpleNamespace:
    defaults = dict(id=1, telegram_id=999, role="admin", is_blocked=False, is_archived=False, permission_grants=[])
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _participant(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=2, telegram_id=555, role="participant", is_blocked=False, is_archived=False, permission_grants=[]
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_app(user) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield SimpleNamespace()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
    return app


class AdminToolsApiAccessTests(unittest.TestCase):
    """Mirrors tests/test_admin_analytics_service.py's API access-control shape:
    a participant is rejected before any service function runs."""

    def test_participant_cannot_read_goals(self) -> None:
        app = _build_app(_participant())
        client = TestClient(app)
        response = client.get("/api/v1/admin/goals")
        self.assertEqual(response.status_code, 403)

    def test_participant_cannot_read_contacts(self) -> None:
        app = _build_app(_participant())
        client = TestClient(app)
        response = client.get("/api/v1/admin/organization-contacts")
        self.assertEqual(response.status_code, 403)

    def test_participant_cannot_read_structure(self) -> None:
        app = _build_app(_participant())
        client = TestClient(app)
        response = client.get("/api/v1/admin/departments/structure")
        self.assertEqual(response.status_code, 403)

    def test_participant_cannot_read_greetings(self) -> None:
        app = _build_app(_participant())
        client = TestClient(app)
        response = client.get("/api/v1/admin/chat-greetings")
        self.assertEqual(response.status_code, 403)

    def test_admin_reads_goals(self) -> None:
        app = _build_app(_admin())
        client = TestClient(app)
        with patch("app.api.v1.admin.list_goals", new=AsyncMock(return_value=[])):
            response = client.get("/api/v1/admin/goals")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_admin_toggles_greeting(self) -> None:
        app = _build_app(_admin())
        client = TestClient(app)
        fake_item = SimpleNamespace(id=1, chat_key="general", title="Общий чат", text="Привет", is_enabled=True, chat_id=None)
        with patch("app.api.v1.admin.toggle_greeting", new=AsyncMock(return_value=fake_item)):
            response = client.post("/api/v1/admin/chat-greetings/1/toggle")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["is_enabled"], True)


if __name__ == "__main__":
    unittest.main()
