from datetime import date, timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.admin_event_create import create_event_draft, save_event_draft_step, publish_event, cancel_event, EventDraftPatch, _publish_broadcast
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

    async def test_changed_event_is_committed_before_notification_and_retry_is_quiet(self):
        async with self.sessions() as session:
            draft = await create_event_draft(self.admin, session)
            await session.commit()
        original = date.today() + timedelta(days=2)
        changed = original + timedelta(days=1)
        async with self.sessions() as session:
            await save_event_draft_step(
                draft.id, EventDraftPatch(title="Встреча ЭРА", short_description="Встречаемся",
                                          location="Дом Москвы", event_date=original),
                self.admin, session, self.settings, None,
            )
            await session.commit()
        async with self.sessions() as session:
            await publish_event(draft.id, self.admin, session, self.settings, None)

        async def check_committed(*args):
            async with self.sessions() as fresh:
                saved = await fresh.get(Event, draft.id)
                self.assertEqual(saved.event_date, changed)

        with patch("app.api.v1.admin_event_create._notify_changed_event",
                   new=AsyncMock(side_effect=check_committed)) as notify:
            async with self.sessions() as session:
                await save_event_draft_step(
                    draft.id, EventDraftPatch(event_date=changed),
                    self.admin, session, self.settings, object(),
                )
            async with self.sessions() as session:
                await save_event_draft_step(
                    draft.id, EventDraftPatch(event_date=changed),
                    self.admin, session, self.settings, object(),
                )
            self.assertEqual(notify.await_count, 1)

    async def test_cancel_is_committed_before_notice_and_double_cancel_is_idempotent(self):
        async with self.sessions() as session:
            draft = await create_event_draft(self.admin, session)
            await session.commit()
        async with self.sessions() as session:
            await save_event_draft_step(
                draft.id, EventDraftPatch(title="Встреча ЭРА", short_description="План",
                                          location="Дом Москвы"),
                self.admin, session, self.settings, None,
            )
            await session.commit()
        async with self.sessions() as session:
            await publish_event(draft.id, self.admin, session, self.settings, None)

        async def check_then_fail(*args):
            async with self.sessions() as fresh:
                saved = await fresh.get(Event, draft.id)
                self.assertEqual(saved.status, EventStatus.CANCELLED)
            raise RuntimeError("telegram unavailable")

        with patch("app.api.v1.admin_event_create._notify_changed_event",
                   new=AsyncMock(side_effect=check_then_fail)) as notify:
            async with self.sessions() as session:
                first = await cancel_event(draft.id, self.admin, session, self.settings, object())
                self.assertEqual(first.status, EventStatus.CANCELLED)
            async with self.sessions() as session:
                second = await cancel_event(draft.id, self.admin, session, self.settings, object())
                self.assertEqual(second.status, EventStatus.CANCELLED)
            self.assertEqual(notify.await_count, 1)
