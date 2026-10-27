from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.media import router
from app.api.v1.media_extras import router as extras
from app.config import Settings
from app.database.base import Base
from app.database.media_models import MediaLibraryItem
from app.database.models import AuditLog, Department, Direction, User, UserDirection
from app.services import media_knowledge_service as knowledge, media_service


class MediaKnowledgeTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.factory() as session:
            users = [User(telegram_id=701 + i, first_name=name, application_status="approved") for i, name in enumerate(("Председатель", "Руководитель", "Участник", "Посторонний"))]
            dept = Department(name="Медиаотдел")
            session.add_all([*users, dept])
            await session.flush()
            direction = Direction(name="Медиа", department_id=dept.id, leader_id=users[1].id)
            session.add(direction)
            await session.flush()
            session.add(UserDirection(user_id=users[2].id, direction_id=direction.id, status="approved"))
            await session.commit()
            self.ids = [u.id for u in users]
            self.direction_id = direction.id
        self.settings = Settings(bot_token="0000000000:CITESTTOKEN", era_chair_user_id=self.ids[0])

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def create(self, session, values=None, key="same"):
        return await knowledge.create_item(session, await session.get(User, self.ids[1]), self.settings,
            values or {"kind": "text", "category": "journalism", "title": "Интервью", "description": "Как подготовить вопросы"}, key)

    async def test_shared_catalogue_idempotency_and_conflicting_replay(self):
        async with self.factory() as session:
            item = await self.create(session)
            repeated = await self.create(session)
            self.assertEqual(item.id, repeated.id)
            self.assertEqual(await session.scalar(select(func.count(MediaLibraryItem.id))), 1)
            self.assertEqual(await session.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == knowledge.ACTIONS[0])), 1)
            self.assertEqual((await media_service.list_library(session))[0].id, item.id)
            with self.assertRaises(ValueError):
                await self.create(session, {"kind": "text", "title": "Другой текст", "description": "Другая инструкция"})

    async def test_revision_pinning_hiding_and_restoring_preserve_original_record(self):
        async with self.factory() as session:
            item = await self.create(session)
            leader = await session.get(User, self.ids[1])
            state = await knowledge.item_out(session, item)
            self.assertGreater(state["revision"], 0)
            await knowledge.update_item(session, leader, self.settings, item.id, {"pinned": True, "is_active": False}, state["revision"])
            self.assertEqual(await knowledge.list_items(session), [])
            self.assertEqual(len(await knowledge.list_items(session, include_archived=True)), 1)
            with self.assertRaisesRegex(ValueError, "Материал уже изменён"):
                await knowledge.update_item(session, leader, self.settings, item.id, {"title": "Старый экран"}, state["revision"])
            state = await knowledge.item_out(session, item)
            self.assertTrue(state["pinned"])
            await knowledge.update_item(session, leader, self.settings, item.id, {"is_active": True}, state["revision"])
            self.assertEqual((await knowledge.list_items(session))[0].id, item.id)

    async def test_untrusted_urls_empty_instructions_and_unknown_routes_are_rejected(self):
        async with self.factory() as session:
            for url in ("javascript:alert(1)", "http://example.org/doc", "https://user:password@example.org/doc", "https://example.org:22/doc", "https://exa mple.org/doc"):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    await self.create(session, {"kind": "link", "title": "Ссылка", "url": url}, key=url)
            for values in ({"kind": "text", "title": "Пустой текст"}, {"kind": "link", "title": "Без ссылки"},
                           {"kind": "text", "title": "Текст", "description": "Текст", "category": "wrong"},
                           {"kind": "guide", "title": "Подмена", "url": "admin/people", "destination_type": "internal_route"}):
                with self.subTest(values=values), self.assertRaises(ValueError):
                    await self.create(session, values)

    async def test_malformed_links_fail_consistently_without_creating_records(self):
        malformed = (
            "https://example.org:abc/doc",
            "https://example.org:99999/doc",
            "https://[broken/doc",
            "https://example.org\\@evil.example/doc",
        )
        async with self.factory() as session:
            for index, url in enumerate(malformed):
                with self.subTest(url=url), self.assertRaisesRegex(
                    ValueError, "^Укажите HTTPS-ссылку на материал$"
                ):
                    await self.create(
                        session, {"kind": "link", "title": "Материал", "url": url},
                        key=f"invalid-link-{index}",
                    )
            self.assertEqual(await session.scalar(select(func.count(MediaLibraryItem.id))), 0)
            item = await self.create(
                session,
                {"kind": "link", "title": "Материал", "url": "https://example.org:443/doc"},
                key="valid-https-port",
            )
            self.assertEqual(item.url, "https://example.org:443/doc")

    async def test_http_malformed_link_has_safe_localized_validation_error(self):
        app = FastAPI()
        app.include_router(extras)
        async def session_override():
            async with self.factory() as session:
                yield session
                await session.commit()
        app.dependency_overrides[get_session] = session_override
        app.dependency_overrides[get_settings] = lambda: self.settings
        async with self.factory() as session:
            leader = await session.get(User, self.ids[1])
        app.dependency_overrides[get_current_user] = lambda: leader
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            result = await client.post("/media/desk/library", json={
                "kind": "link", "title": "Материал", "url": "https://example.org:abc/doc",
                "request_key": "00000000-0000-4000-8000-000000000002",
            })
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.json()["detail"], "Укажите HTTPS-ссылку на материал")
        async with self.factory() as session:
            self.assertEqual(await session.scalar(select(func.count(MediaLibraryItem.id))), 0)

    async def test_member_and_old_leader_form_cannot_edit(self):
        async with self.factory() as session:
            item = await self.create(session)
            state = await knowledge.item_out(session, item)
            member = await session.get(User, self.ids[2])
            with self.assertRaises(PermissionError):
                await knowledge.update_item(session, member, self.settings, item.id, {"pinned": True}, state["revision"])
            direction = await session.get(Direction, self.direction_id)
            direction.leader_id = None
            await session.flush()
            with self.assertRaises(PermissionError):
                await knowledge.update_item(session, await session.get(User, self.ids[1]), self.settings, item.id, {"pinned": True}, state["revision"])

    async def test_seed_does_not_recreate_renamed_hidden_default_after_restart(self):
        async with self.factory() as session:
            await media_service.seed_media_os(session, self.settings)
            initial = await session.scalar(select(func.count(MediaLibraryItem.id)))
            item = await session.scalar(select(MediaLibraryItem).where(MediaLibraryItem.kind == "template"))
            self.assertIsNotNone(item)
            item_id = item.id
            revision = await knowledge.revision(session, item_id)
            await knowledge.update_item(session, await session.get(User, self.ids[1]), self.settings, item_id,
                {"title": "Новые шаблоны команды", "url": "https://www.canva.com/new-templates", "is_active": False}, revision)
            await session.commit()
        async with self.factory() as session:
            await media_service.seed_media_os(session, self.settings)
            self.assertEqual(await session.scalar(select(func.count(MediaLibraryItem.id))), initial)
            item = await session.get(MediaLibraryItem, item_id)
            self.assertEqual(item.title, "Новые шаблоны команды")
            self.assertFalse(item.is_active)

    async def test_catalogue_bulk_revisions_include_archived_and_avoid_n_plus_one(self):
        async with self.factory() as session:
            first = await self.create(session, key="bulk-first")
            second = await self.create(session, {
                "kind": "text", "category": "texts", "title": "Тексты команды",
                "description": "Правила публикации",
            }, key="bulk-second")
            third = await self.create(session, {
                "kind": "text", "category": "design", "title": "Визуальные правила",
                "description": "Размеры и шрифты",
            }, key="bulk-third")
            leader = await session.get(User, self.ids[1])
            second_revision = await knowledge.revision(session, second.id)
            await knowledge.update_item(session, leader, self.settings, second.id,
                {"is_active": False, "pinned": True}, second_revision)
            await session.flush()

            selects = []
            def count_select(conn, cursor, statement, parameters, context, executemany):
                if statement.lstrip().upper().startswith("SELECT"):
                    selects.append(statement)
            event.listen(self.engine.sync_engine, "before_cursor_execute", count_select)
            try:
                active = await knowledge.list_items_out(session)
            finally:
                event.remove(self.engine.sync_engine, "before_cursor_execute", count_select)
            self.assertEqual(len(selects), 2, "Catalogue must not query revisions for each item")
            self.assertEqual({row["id"] for row in active}, {first.id, third.id})
            self.assertTrue(all(row["revision"] > 0 for row in active))

            all_items = await knowledge.list_items_out(session, include_archived=True)
            self.assertEqual({row["id"] for row in all_items}, {first.id, second.id, third.id})
            hidden = next(row for row in all_items if row["id"] == second.id)
            self.assertFalse(hidden["is_active"])
            self.assertTrue(hidden["pinned"])
            self.assertEqual(hidden["revision"], await knowledge.revision(session, second.id))

    async def test_http_catalogue_and_archived_access(self):
        app = FastAPI()
        app.include_router(router)
        app.include_router(extras)
        async def session_override():
            async with self.factory() as session:
                yield session
                await session.commit()
        app.dependency_overrides[get_session] = session_override
        app.dependency_overrides[get_settings] = lambda: self.settings
        async with self.factory() as session:
            leader, member, outsider = [await session.get(User, i) for i in self.ids[1:]]
        app.dependency_overrides[get_current_user] = lambda: leader
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            payload = {"kind": "text", "category": "texts", "title": "Как написать пост", "description": "Начните с мысли", "request_key": "00000000-0000-4000-8000-000000000001"}
            result = await client.post("/media/desk/library", json=payload)
            self.assertEqual(result.status_code, 200, result.text)
            state = result.json()
            self.assertEqual((await client.post("/media/desk/library", json=payload)).json()["id"], state["id"])
            app.dependency_overrides[get_current_user] = lambda: member
            self.assertEqual((await client.get("/media/library")).json()[0]["category"], "texts")
            self.assertEqual((await client.get("/media/library?include_archived=true")).status_code, 403)
            self.assertEqual((await client.patch(f"/media/desk/library/{state['id']}", json={"revision": state["revision"], "is_active": False})).status_code, 403)
            app.dependency_overrides[get_current_user] = lambda: leader
            hidden = await client.patch(f"/media/desk/library/{state['id']}", json={"revision": state["revision"], "is_active": False})
            self.assertEqual(hidden.status_code, 200, hidden.text)
            self.assertEqual((await client.get("/media/library")).json(), [])
            self.assertFalse((await client.get("/media/library?include_archived=true")).json()[0]["is_active"])
            app.dependency_overrides[get_current_user] = lambda: outsider
            self.assertEqual((await client.get("/media/library")).status_code, 403)

    async def test_native_bot_hides_archived_items_and_checks_current_membership(self):
        from app.handlers.media_management import knowledge_command, knowledge_item
        async with self.factory() as session:
            item = await self.create(session)
            member = await session.get(User, self.ids[2])
            message = SimpleNamespace(from_user=SimpleNamespace(id=member.telegram_id), text="/media_knowledge вопросы", answer=AsyncMock())
            await knowledge_command(message, member, session, self.settings)
            markup = message.answer.call_args.kwargs["reply_markup"]
            self.assertEqual(markup.inline_keyboard[0][0].callback_data, f"media:knowledge:{item.id}")
            item.is_active = False
            await session.flush()
            call = SimpleNamespace(from_user=message.from_user, data=f"media:knowledge:{item.id}", answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()))
            await knowledge_item(call, member, session, self.settings)
            call.message.answer.assert_not_awaited()
            call.answer.assert_awaited_with("Материал скрыт или недоступен.", show_alert=True)

    async def test_native_knowledge_internal_route_keeps_telegram_webapp_context(self):
        from app.handlers.media_management import knowledge_item
        async with self.factory() as session:
            item = await self.create(session, {
                "kind": "guide", "category": "guides", "title": "Гид медиа",
                "url": "media/guide", "destination_type": "internal_route",
            }, key="native-internal-guide")
            member = await session.get(User, self.ids[2])
            call = SimpleNamespace(
                from_user=SimpleNamespace(id=member.telegram_id),
                data=f"media:knowledge:{item.id}",
                answer=AsyncMock(),
                message=SimpleNamespace(answer=AsyncMock()),
            )
            self.settings.miniapp_url = "https://era.example/app/"
            self.settings.miniapp_auth_secret = "test-secret"
            await knowledge_item(call, member, session, self.settings)
            button = call.message.answer.await_args_list[-1].kwargs["reply_markup"].inline_keyboard[0][0]
            self.assertIsNone(button.url)
            self.assertIn("eraPath=media%2Fguide", button.web_app.url)
            self.assertTrue(button.web_app.url.startswith("https://era.example/app/"))

            # Without a configured Mini App the handler explains the problem,
            # never emits an external link to an internal route.
            self.settings.miniapp_auth_secret = ""
            call.message.answer.reset_mock()
            await knowledge_item(call, member, session, self.settings)
            self.assertIn("временно недоступен", call.message.answer.await_args_list[-1].args[0])
            self.assertNotIn("reply_markup", call.message.answer.await_args_list[-1].kwargs)
