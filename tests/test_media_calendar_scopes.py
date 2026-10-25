from unittest import IsolatedAsyncioTestCase

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.media_workspace import router
from app.config import Settings
from app.database.base import Base
from app.database.models import AuditLog, Department, Direction, PermissionGrant, User, UserDirection
from app.services import media_leadership_service as leadership
from app.services import media_scope_service as scopes
from app.services import media_service, media_workspace_service as workspace
from app.services.media_membership_service import request_join


class CalendarScopeTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.factory() as session:
            users = [User(telegram_id=501 + i, first_name=name, application_status="approved")
                     for i, name in enumerate(("Председатель", "Руководитель", "Редактор", "Другой", "Посторонний"))]
            dept = Department(name="Внешние связи")
            session.add_all([*users, dept])
            await session.flush()
            direction = Direction(name="Медиа", department_id=dept.id, leader_id=users[1].id)
            session.add(direction)
            await session.flush()
            session.add_all([UserDirection(user_id=user.id, direction_id=direction.id, status="approved") for user in users[1:4]])
            await session.commit()
            self.ids = [user.id for user in users]
            self.direction_id = direction.id
        self.settings = Settings(bot_token="0000000000:CITESTTOKEN", era_chair_user_id=self.ids[0])

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def users(self, session):
        return [await session.get(User, ident) for ident in self.ids]

    async def grant(self, session, area="era", revision=0):
        _, leader, editor, *_ = await self.users(session)
        return await scopes.set_editor(session, leader, self.settings, area, editor.id, True, revision)

    async def test_editor_can_only_write_own_area_and_cannot_delegate_or_open_desk(self):
        async with self.factory() as session:
            state = await self.grant(session)
            _, leader, editor, other, outsider = await self.users(session)
            self.assertEqual(state["editors"][0]["id"], editor.id)
            item = await workspace.create_entry(session, editor, self.settings, "era", {"title": "Материал", "platform": "telegram"}, "own")
            await workspace.update_entry(session, editor, self.settings, "era", item.id, {"status": "review"}, 0)
            with self.assertRaises(PermissionError):
                await workspace.create_entry(session, editor, self.settings, "ksoors", {"title": "Подмена"}, "other")
            ksoors = await workspace.create_entry(session, leader, self.settings, "ksoors", {"title": "Чужой материал", "platform": "telegram"}, "ksoors")
            with self.assertRaises(LookupError):
                await workspace.update_entry(session, editor, self.settings, "era", ksoors.id, {"status": "ready"}, 0)
            with self.assertRaises(PermissionError):
                await scopes.set_editor(session, editor, self.settings, "era", other.id, True, state["revision"])
            with self.assertRaises(PermissionError):
                await scopes.scope_state(session, editor, self.settings, "era")
            self.assertFalse(await media_service.can_manage_media(session, editor, self.settings))
            self.assertEqual(await media_service.media_access_level(session, editor, self.settings), "member")
            with self.assertRaises(ValueError):
                await scopes.set_editor(session, leader, self.settings, "era", outsider.id, True, state["revision"])

    async def test_stale_confirmation_cannot_restore_revoked_right_and_retry_has_one_audit(self):
        async with self.factory() as session:
            state = await self.grant(session)
            repeated = await self.grant(session)
            self.assertEqual(state, repeated)
            self.assertEqual(await session.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == scopes.ACTION)), 1)
            _, leader, editor, *_ = await self.users(session)
            revoked = await scopes.set_editor(session, leader, self.settings, "era", editor.id, False, state["revision"])
            self.assertEqual(revoked["editors"], [])
            with self.assertRaisesRegex(ValueError, "Полномочия уже изменены"):
                await self.grant(session, revision=state["revision"])
            self.assertFalse(await scopes.can_edit_calendar(session, editor, self.settings, "era"))
            self.assertEqual((await scopes.set_editor(session, leader, self.settings, "era", editor.id, False, state["revision"])), revoked)

    async def test_membership_revoke_and_rejoin_do_not_restore_grants(self):
        async with self.factory() as session:
            await self.grant(session)
            _, leader, editor, *_ = await self.users(session)
            await media_service.decide_media_application(session, editor.id, "revoke", actor=leader, settings=self.settings)
            self.assertFalse(await scopes.can_edit_calendar(session, editor, self.settings, "era"))
            self.assertEqual(await request_join(session, editor.telegram_id, editor), "joined")
            self.assertFalse(await scopes.can_edit_calendar(session, editor, self.settings, "era"))
            grant = await session.scalar(select(PermissionGrant))
            self.assertFalse(grant.is_active)

    async def test_leader_replacement_revokes_delegation_even_if_old_leader_reappointed(self):
        async with self.factory() as session:
            await self.grant(session)
            chair, leader, editor, other, _ = await self.users(session)
            await leadership.change_leader(session, chair, self.settings, target_telegram_id=other.telegram_id, expected_revision=0)
            self.assertFalse(await scopes.can_edit_calendar(session, editor, self.settings, "era"))
            _, revision = await leadership.leadership_state(session)
            await leadership.change_leader(session, chair, self.settings, target_telegram_id=leader.telegram_id, expected_revision=revision)
            self.assertFalse(await scopes.can_edit_calendar(session, editor, self.settings, "era"))
            with self.assertRaises(PermissionError):
                await scopes.set_editor(session, other, self.settings, "era", editor.id, True, 0)

    async def test_cached_editor_and_grantor_are_refreshed_and_inactive_accounts_denied(self):
        async with self.factory() as session:
            await self.grant(session)
            await session.commit()
            _, leader, editor, *_ = await self.users(session)
            async with self.factory() as second:
                await second.execute(update(User).where(User.id == leader.id).values(is_blocked=True))
                await second.commit()
            self.assertFalse(await scopes.can_edit_calendar(session, editor, self.settings, "era"))
            with self.assertRaises(PermissionError):
                await self.grant(session)
            leader.is_blocked = False
            await session.commit()
            for field, value in (("is_blocked", True), ("is_archived", True), ("application_status", "pending")):
                original = getattr(editor, field)
                setattr(editor, field, value)
                await session.flush()
                self.assertFalse(await scopes.can_edit_calendar(session, editor, self.settings, "era"))
                setattr(editor, field, original)
                await session.flush()
            self.assertFalse(await scopes.can_edit_calendar(session, editor, self.settings, "unknown"))
            self.assertFalse(await scopes.can_edit_calendar(session, None, self.settings, "era"))

    async def test_http_editor_uses_minimal_team_endpoint_but_not_global_desk(self):
        from app.api.v1.media import router as desk
        app = FastAPI()
        app.include_router(router)
        app.include_router(desk)
        async def session_override():
            async with self.factory() as session:
                yield session
                await session.commit()
        app.dependency_overrides[get_session] = session_override
        app.dependency_overrides[get_settings] = lambda: self.settings
        async with self.factory() as session:
            chair, leader, editor, other, outsider = await self.users(session)
        app.dependency_overrides[get_current_user] = lambda: leader
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            result = await client.post("/media/workspaces/era/editors", json={"user_id": editor.id, "enabled": True, "revision": 0})
            self.assertEqual(result.status_code, 200, result.text)
            revision = result.json()["revision"]
            app.dependency_overrides[get_current_user] = lambda: editor
            areas = (await client.get("/media/workspaces")).json()
            self.assertEqual([(x["id"], x["can_manage"], x["can_assign_editors"]) for x in areas], [("era", True, False), ("ksoors", False, False)])
            team = await client.get("/media/workspaces/era/team")
            self.assertEqual(team.status_code, 200)
            self.assertTrue(all(set(member) == {"id", "name"} for member in team.json()))
            for path in ("/media/workspaces/era/editors", "/media/team/members", "/media/desk/analytics"):
                self.assertEqual((await client.get(path)).status_code, 403, path)
            self.assertEqual((await client.post("/media/workspaces/era/editors", json={"user_id": other.id, "enabled": True, "revision": revision})).status_code, 403)
            payload = {"request_key": "00000000-0000-4000-8000-000000000001", "title": "Редакторский материал", "responsible_id": other.id}
            created = await client.post("/media/workspaces/era/calendar", json=payload)
            self.assertEqual(created.status_code, 200, created.text)
            self.assertEqual((await client.post("/media/workspaces/ksoors/calendar", json=payload)).status_code, 403)
            app.dependency_overrides[get_current_user] = lambda: chair
            self.assertEqual((await client.post("/media/workspaces/era/editors", json={"user_id": editor.id, "enabled": False, "revision": revision})).status_code, 200)
            app.dependency_overrides[get_current_user] = lambda: editor
            self.assertEqual((await client.patch(f"/media/workspaces/era/calendar/{created.json()['id']}", json={"revision": 0, "status": "ready"})).status_code, 403)
            app.dependency_overrides[get_current_user] = lambda: outsider
            self.assertEqual((await client.get("/media/workspaces/era/team")).status_code, 403)
