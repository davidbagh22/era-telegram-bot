from datetime import date, timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.admin_event_create import create_event_draft, save_event_draft_step, publish_event, EventDraftPatch, _publish_broadcast
from app.config import Settings
from app.database.base import Base
from app.database.models import Event, User
from app.utils.constants import EventStatus


class EventWizardPublishTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token="1234567890:test-token", bot_username="ERA_1bot", general_chat_id=-100123)
        async with self.sessions() as session:
            user = User(telegram_id=1, first_name="Admin", phone="+10000001", personal_data_consent=True, is_channel_subscribed=True, role="admin")
            session.add(user)
            await session.commit()
            self.admin = user

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_short_description_publish_survives_telegram_failure_and_reload(self):
        async with self.sessions() as session:
            draft = await create_event_draft(self.admin, session)
            await session.commit()
        async with self.sessions() as session:
            await save_event_draft_step(draft.id, EventDraftPatch(title="Встреча ЭРА", short_description="Программа встречи", full_description="", location="Дом Москвы", event_date=date.today()+timedelta(days=2)), self.admin, session, self.settings, None)
            await session.commit()
        with patch("app.api.v1.admin_event_create._publish_broadcast", new=AsyncMock(side_effect=RuntimeError("transport"))) as notify:
            async with self.sessions() as session:
                result = await publish_event(draft.id, self.admin, session, self.settings, object())
                self.assertEqual(result.status, EventStatus.REGISTRATION_OPEN)
            async with self.sessions() as session:
                saved = await session.get(Event, draft.id)
                self.assertEqual(saved.description, "Программа встречи")
                self.assertEqual(saved.status, EventStatus.REGISTRATION_OPEN)
                again = await publish_event(draft.id, self.admin, session, self.settings, object())
                self.assertEqual(again.id, draft.id)
            self.assertEqual(notify.await_count, 1)

    async def test_publication_uses_group_safe_button_and_announcements_topic(self):
        event = SimpleNamespace(id=4, title="Event", description="Description", event_date=date.today(), event_time=__import__('datetime').time(18), location="Hall")
        experience = SimpleNamespace(broadcast_enabled=False, broadcast_targets=[], short_description="Short")
        with patch("app.api.v1.admin_event_create.send_general_topic", new=AsyncMock(return_value=True)) as send:
            await _publish_broadcast(object(), self.settings, None, event, experience)
            self.assertEqual(send.call_args.args[2], "announcements")
            button = send.call_args.kwargs["reply_markup"].inline_keyboard[0][0]
            self.assertIsNone(button.web_app)
            self.assertIn("startapp=event_4", button.url)
