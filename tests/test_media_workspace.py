from datetime import datetime, timezone
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.media_workspace import CalendarCreate, CalendarUpdate
from app.config import Settings
from app.database.base import Base
from app.database.media_models import MediaContentItem
from app.database.models import Department, Direction, User, UserDirection
from app.services import media_service
from app.services import media_workspace_service as workspace


class MediaWorkspaceTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def seed(self, session):
        chair, leader, member, outsider = [User(telegram_id=100 + index, first_name="Участник", application_status="approved") for index in range(4)]
        department = Department(name="Медиаотдел")
        session.add_all([chair, leader, member, outsider, department])
        await session.flush()
        direction = Direction(name="Медиа", department_id=department.id, leader_id=leader.id)
        session.add(direction)
        await session.flush()
        session.add_all([UserDirection(user_id=user.id, direction_id=direction.id, status="approved") for user in (leader, member)])
        await session.flush()
        return Settings(bot_token="0000000000:CITESTTOKEN", era_chair_user_id=chair.id), chair, leader, member, outsider, direction

    async def create(self, session, user, settings, area="era", key="first"):
        return await workspace.create_entry(session, user, settings, area,
            {"title": "Репортаж", "body": "Описание", "platform": "telegram", "scheduled_at": datetime(2026, 10, 25, 15, tzinfo=timezone.utc)}, key)

    async def test_idempotency_area_isolation_and_legacy_content(self):
        async with self.factory() as session:
            settings, _, leader, _, _, _ = await self.seed(session)
            item = await self.create(session, leader, settings)
            repeat = await self.create(session, leader, settings)
            self.assertEqual(item.id, repeat.id)
            other = await self.create(session, leader, settings, "ksoors", "second")
            legacy = MediaContentItem(source_key="legacy", source_kind="manual", kind="text", status="planned", title="Старый план")
            session.add(legacy)
            await session.flush()
            self.assertEqual({row["id"] for row in await workspace.calendar(session, "era")}, {item.id, legacy.id})
            self.assertEqual([row["id"] for row in await workspace.calendar(session, "ksoors")], [other.id])
            with self.assertRaises(ValueError):
                await self.create(session, leader, settings, "ksoors")
            with self.assertRaises(LookupError):
                await workspace.update_entry(session, leader, settings, "era", other.id, {"title": "Подмена"}, 0)

    async def test_calendar_paginates_beyond_100_without_crossing_areas(self):
        async with self.factory() as session:
            settings, _, leader, _, _, _ = await self.seed(session)
            session.add_all([
                MediaContentItem(source_key=f"workspace:era:page:{index}", source_kind="media_workspace",
                    status="planned", created_by=leader.id, metadata_json={"media_area": "era"})
                for index in range(105)
            ] + [
                MediaContentItem(source_key=f"workspace:ksoors:page:{index}", source_kind="media_workspace",
                    status="planned", created_by=leader.id, metadata_json={"media_area": "ksoors"})
                for index in range(3)
            ])
            await session.flush()
            first = await workspace.calendar(session, "era")
            second = await workspace.calendar(session, "era", before_id=first[-1]["id"])
            self.assertEqual((len(first), len(second)), (100, 5))
            self.assertFalse({row["id"] for row in first} & {row["id"] for row in second})
            self.assertEqual(len(await workspace.calendar(session, "ksoors")), 3)
            self.assertEqual(await workspace.calendar(session, "era", before_id=second[-1]["id"]), [])

    async def test_http_creation_persists_and_member_cannot_mutate(self):
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient
        from app.api.deps import get_current_user, get_session, get_settings
        from app.api.v1.media_workspace import router
        from app.api.v1.media import router as legacy_router
        from app.api.v1.media_extras import router as extras_router
        async with self.factory() as session:
            settings, _, leader, member, _, _ = await self.seed(session)
            await session.commit()
            app = FastAPI()
            app.include_router(router)
            app.include_router(legacy_router)
            app.include_router(extras_router)
            async def session_override():
                async with self.factory() as current:
                    yield current
                    await current.commit()
            app.dependency_overrides[get_session] = session_override
            app.dependency_overrides[get_settings] = lambda: settings
            app.dependency_overrides[get_current_user] = lambda: leader
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                payload = {"request_key": "00000000-0000-4000-8000-000000000001", "title": "Новый материал", "scheduled_at": "2026-10-25T19:00:00+04:00"}
                first = await client.post("/media/workspaces/ksoors/calendar", json=payload)
                self.assertEqual(first.status_code, 200, first.text)
                repeat = await client.post("/media/workspaces/ksoors/calendar", json=payload)
                self.assertEqual(repeat.json()["id"], first.json()["id"])
                listing = await client.get("/media/workspaces/ksoors/calendar")
                self.assertEqual(len(listing.json()), 1)
                self.assertEqual((await client.get("/media/workspaces/ksoors/calendar?before_id=0")).status_code, 422)
                self.assertEqual((await client.get(f"/media/workspaces/ksoors/calendar?before_id={listing.json()[0]['id']}")).json(), [])
                self.assertTrue(listing.json()[0]["scheduled_at"].endswith("+00:00"))
                self.assertEqual((await client.get("/media/workspaces/era/calendar")).json(), [])
                item_id = first.json()["id"]
                for method, path, values in (
                    ("PATCH", f"/media/desk/content/{item_id}", {"body": "Обход версии"}),
                    ("POST", f"/media/desk/content/{item_id}/reschedule", {"scheduled_at": "2026-11-02T19:00:00+04:00"}),
                    ("POST", f"/media/desk/content/{item_id}/skip", {}),
                    ("PATCH", f"/media/desk/content/{item_id}/pipeline", {"status": "PUBLISHED"}),
                ):
                    response = await client.request(method, path, json=values)
                    self.assertEqual(response.status_code, 409, response.text)
                listing = (await client.get("/media/workspaces/ksoors/calendar")).json()[0]
                self.assertEqual((listing["revision"], listing["status"]), (0, "planned"))
                app.dependency_overrides[get_current_user] = lambda: member
                self.assertEqual((await client.get("/media/workspaces/ksoors/calendar")).status_code, 200)
                self.assertEqual((await client.patch(f"/media/workspaces/ksoors/calendar/{first.json()['id']}", json={"revision": 0, "status": "ready"})).status_code, 403)

    async def test_members_read_but_cannot_write_and_revoked_leader_form_fails(self):
        async with self.factory() as session:
            settings, _, leader, member, outsider, direction = await self.seed(session)
            item = await self.create(session, leader, settings)
            await workspace.require_access(session, member, settings)
            for user in (member, outsider):
                with self.assertRaises(PermissionError):
                    await self.create(session, user, settings, key=f"denied-{user.id}")
            with self.assertRaises(PermissionError):
                await workspace.require_access(session, outsider, settings)
            direction.leader_id = None
            await session.flush()
            with self.assertRaises(PermissionError):
                await workspace.update_entry(session, leader, settings, "era", item.id, {"status": "ready"}, 0)

    async def test_publication_requires_approval_valid_link_and_audit_revision(self):
        async with self.factory() as session:
            settings, _, leader, _, _, _ = await self.seed(session)
            item = await self.create(session, leader, settings)
            with self.assertRaises(ValueError):
                await workspace.update_entry(session, leader, settings, "era", item.id, {"status": "published", "publication_url": "https://t.me/era_leaders1/1"}, 0)
            await workspace.update_entry(session, leader, settings, "era", item.id, {"status": "review"}, 0)
            with self.assertRaises(ValueError):
                await workspace.update_entry(session, leader, settings, "era", item.id, {"status": "ready"}, 0)
            await workspace.update_entry(session, leader, settings, "era", item.id, {"status": "ready"}, 1)
            from app.services.media_pipeline_service import reconcile_content_state
            await reconcile_content_state(session, item)
            self.assertEqual(item.status, "ready")
            for url in (None, "javascript:alert(1)", "https://evil.test/1", "https://t.me/era_leaders1"):
                with self.assertRaises(ValueError):
                    await workspace.update_entry(session, leader, settings, "era", item.id, {"status": "published", "publication_url": url}, 2)
            self.assertIsNone(item.published_at)
            await workspace.update_entry(session, leader, settings, "era", item.id,
                {"status": "published", "publication_url": "https://t.me/era_leaders1/123"}, 2)
            self.assertEqual(item.status, "published")
            self.assertEqual(workspace.item_out(item)["publication_evidence"], "manager_confirmed_link")
            self.assertIsNotNone(item.published_at)
            with self.assertRaises(ValueError):
                await workspace.update_entry(session, leader, settings, "era", item.id, {"title": "После выпуска"}, 3)

    async def test_legacy_publisher_never_sends_ksoors_or_unapproved_workspace_to_era(self):
        async with self.factory() as session:
            settings, _, leader, _, _, _ = await self.seed(session)
            bot = AsyncMock()
            item = await self.create(session, leader, settings, "ksoors")
            result = await media_service.publish_content(session, bot, settings, item, manual=True)
            self.assertFalse(result.ok)
            item.metadata_json = {**item.metadata_json, "media_area": "era"}
            result = await media_service.publish_content(session, bot, settings, item, manual=True)
            self.assertEqual(result.code, "editorial_approval_required")
            bot.send_message.assert_not_awaited()
            self.assertEqual(await session.scalar(select(func.count(MediaContentItem.id))), 1)

    async def test_calendar_managed_legacy_state_survives_reconciliation_and_old_mutators(self):
        from app.services.media_pipeline_service import reconcile_content_state
        async with self.factory() as session:
            settings, _, leader, _, _, _ = await self.seed(session)
            item = MediaContentItem(source_key="old-calendar", source_kind="manual", kind="text", status="planned", title="Старый материал")
            session.add(item)
            await session.flush()
            await workspace.update_entry(session, leader, settings, "era", item.id, {"status": "review"}, 0)
            await reconcile_content_state(session, item)
            self.assertEqual(item.status, "review")
            for managed in (item, await self.create(session, leader, settings)):
                with self.assertRaises(ValueError):
                    await media_service.reschedule_content(session, managed, datetime.now(timezone.utc))
                with self.assertRaises(ValueError):
                    await media_service.skip_content(session, managed)
            self.assertEqual(item.metadata_json["workspace_revision"], 1)

    def test_dates_require_explicit_timezone_and_convert_yerevan_to_utc(self):
        from pydantic import ValidationError
        for model, values in ((CalendarCreate, {"request_key": "00000000-0000-4000-8000-000000000001", "title": "Репортаж"}), (CalendarUpdate, {"revision": 0})):
            with self.assertRaises(ValidationError):
                model(**values, scheduled_at="2026-10-25T19:00:00")
            item = model(**values, scheduled_at="2026-10-25T19:00:00+04:00")
            self.assertEqual(item.scheduled_at.hour, 15)
