from datetime import time
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_user, get_session
from app.api.v1 import events
from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import AppSetting, Event, EventRegistration, User
from app.handlers import anniversary as handler
from app.handlers.participant.navigation import _send_main_menu
from app.services import anniversary_registration_service as rsvp
from app.utils.constants import ApplicationStatus, EventStatus


class AnniversaryOneClickTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.addAsyncCleanup(engine.dispose)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(engine, expire_on_commit=False)
        async with self.factory() as session:
            owner = User(
                first_name="Анна", last_name="Иванова", education_work="ЭРА",
                telegram_id=123, application_status=ApplicationStatus.APPROVED,
            )
            guest = User(first_name="Ани", telegram_id=234, application_status=ApplicationStatus.APPROVED)
            session.add_all([owner, guest])
            await session.flush()
            event = Event(
                title="12 декабря для ЭРА — особенная дата.", description="Приглашение",
                event_date=rsvp.START.date(), event_time=time(18), location="Дом Москвы в Ереване",
                created_by=owner.id, status=EventStatus.PUBLISHED, format="Очно",
            )
            session.add(event)
            await session.flush()
            session.add(EventExperience(event_id=event.id, registration_required=False))
            await session.commit()
            self.event_id = event.id
            self.user_id = owner.id
            self.guest_id = guest.id

        async def session_override():
            async with self.factory() as session:
                yield session
                await session.commit()

        async def user_override(session=Depends(get_session)):
            return await session.get(User, self.user_id)

        app = FastAPI()
        app.include_router(events.router)
        app.dependency_overrides[get_session] = session_override
        app.dependency_overrides[get_current_user] = user_override
        self.client = await self.enterAsyncContext(AsyncClient(transport=ASGITransport(app), base_url="http://test"))
        self.enterContext(patch.object(rsvp, "registration_open", return_value=True))

    async def test_profile_click_persists_once_and_appears_in_my_events(self):
        path = f"/events/{self.event_id}"
        event = (await self.client.get(path)).json()
        self.assertTrue(event["anniversary_registration_open"])
        self.assertFalse(event["anniversary_registered"])
        self.assertFalse(event["can_register"])
        self.assertEqual(event["anniversary_defaults"]["organization"], "ЭРА")

        first = await self.client.post(f"{path}/anniversary-rsvp", json={})
        repeated = await self.client.post(f"{path}/anniversary-rsvp", json={"first_name": "Другое"})
        for result in (first, repeated):
            self.assertEqual(result.status_code, 200, result.text)
            self.assertTrue(result.json()["anniversary_registered"])
            self.assertEqual(result.json()["registered_count"], 1)
        mine = await self.client.get("/events", params={"scope": "mine"})
        self.assertEqual([item["id"] for item in mine.json()], [self.event_id])
        async with self.factory() as session:
            self.assertEqual((await rsvp.get_registration(session, 123))["first_name"], "Анна")
            self.assertEqual(await session.scalar(select(func.count()).select_from(EventRegistration)), 0)
            self.assertEqual(await session.scalar(select(func.count()).select_from(AppSetting)), 1)

    async def test_incomplete_profile_uses_form_and_closed_event_rejects_new_signup(self):
        self.user_id = self.guest_id
        path = f"/events/{self.event_id}"
        response = await self.client.post(f"{path}/anniversary-rsvp", json={})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "anniversary_profile_incomplete")
        with patch.object(rsvp, "registration_open", return_value=False):
            response = await self.client.post(f"{path}/anniversary-rsvp", json={"last_name": "Аванесян", "organization": "НКО"})
        self.assertEqual(response.json()["detail"], "anniversary_registration_closed")
        response = await self.client.post(f"{path}/anniversary-rsvp", json={"last_name": "Аванесян", "organization": "НКО"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["anniversary_registered"])

    async def test_legacy_registration_is_retained_in_status_and_export(self):
        async with self.factory() as session:
            session.add(EventRegistration(event_id=self.event_id, user_id=self.user_id))
            await session.commit()
        response = await self.client.post(f"/events/{self.event_id}/anniversary-rsvp", json={})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["anniversary_registered"])
        async with self.factory() as session:
            self.assertIsNone(await rsvp.get_registration(session, 123))
            self.assertEqual([row["telegram_id"] for row in await rsvp.roster(session)], [123])

    async def test_bot_menu_puts_anniversary_first_and_registers_once(self):
        async with self.factory() as session:
            user = await session.get(User, self.user_id)
            message = SimpleNamespace(from_user=SimpleNamespace(id=user.telegram_id), answer=AsyncMock())
            state = AsyncMock()
            with patch.object(rsvp, "featured_event", AsyncMock(return_value=await session.get(Event, self.event_id))):
                await _send_main_menu(message, user, session=session)
                self.assertEqual(message.answer.call_args.kwargs["reply_markup"].keyboard[0][0].text, rsvp.MENU_BUTTON)
                await handler.menu_registration(message, state, session, user)
                self.assertIn("Вы зарегистрированы", message.answer.call_args.args[0])
                await handler.menu_registration(message, state, session, user)
                self.assertIn("Вы уже зарегистрированы", message.answer.call_args.args[0])
