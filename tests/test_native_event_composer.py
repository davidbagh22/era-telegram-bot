import json
from datetime import date, time
from html import unescape
from unittest import IsolatedAsyncioTestCase

from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import AppSetting, Event, User
from app.handlers.leader.event_quick_composer import (
    FIELDS,
    enabled,
    missing,
    parse_announcement,
    save_form,
    signature,
)
from app.handlers.leader.events_block6 import mode_keyboard
from app.services.event_publication_service import escaped_text_parts


def test_pasted_event_text_keeps_full_copy_and_extracts_only_unambiguous_details():
    raw = (
        "Вечер ЭРА <встреча>\n\nБольшой текст анонса & подробности.\n"
        "Дата: 07.11.2026\nВремя: 18:00\n📍 Дом Москвы\nМест: 30"
    )

    form = parse_announcement(raw)

    assert form["description"] == raw
    assert form["title"] == "Вечер ЭРА <встреча>"
    assert form["date"] == date(2026, 11, 7).isoformat()
    assert form["time"] == time(18, 0).isoformat(timespec="minutes")
    assert form["location"] == "Дом Москвы"
    assert form["limit"] == 30


def test_ambiguous_or_invalid_schedule_is_left_for_explicit_editing():
    form = parse_announcement(
        "Встреча\nДата: 07.11.2026 и 08.11.2026\nВремя: 18:00 и 19:00"
    )

    assert "date" not in form
    assert "time" not in form
    assert set(missing(form)) == {"date", "time", "location"}


def test_composer_flag_is_off_by_default_and_testers_are_explicit():
    settings = Settings(bot_token="1234567890:test-token")
    assert not enabled(settings, 1593868942)

    settings.feature_native_event_composer = "TESTERS"
    settings.native_event_composer_tester_ids = [1593868942]
    assert enabled(settings, 1593868942)
    assert not enabled(settings, 1593868943)


def test_enabled_manager_menu_offers_quick_and_advanced_modes():
    settings = Settings(
        bot_token="1234567890:test-token",
        feature_native_event_composer="TESTERS",
        native_event_composer_tester_ids=[1593868942],
    )
    manager = type("Manager", (), {
        "id": 1,
        "telegram_id": 1593868942,
        "role": "admin",
        "is_blocked": False,
        "is_archived": False,
        "permission_grants": [],
    })()

    markup = mode_keyboard(settings, manager)
    assert isinstance(markup, InlineKeyboardMarkup)
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert callbacks == [
        "leader:eventq:new",
        "leader:event6:mode:constructor",
        "leader:eventq:drafts",
    ]
    assert len(FIELDS) == 6


def test_form_signature_changes_when_any_published_value_changes():
    first = {"title": "Встреча", "description": "Текст", "date": "2026-11-07"}
    changed = {**first, "description": "Исправленный текст"}

    assert signature(first) != signature(changed)


def test_html_entities_stay_intact_and_caption_is_bounded():
    original = "<>&" * 1800
    parts = escaped_text_parts(original, first_limit=1000)

    assert all(len(part.encode("utf-16-le")) // 2 <= limit for part, limit in zip(parts, [1000] + [4000] * (len(parts) - 1)))
    assert unescape("".join(parts)) == original


class QuickDraftPersistenceTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token="1234567890:test-token")
        async with self.sessions() as session:
            self.manager = User(telegram_id=1593868942, first_name="Manager", phone="+10000001", role="admin")
            session.add(self.manager)
            await session.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_repeated_edits_reuse_one_existing_event_draft(self):
        form = {
            "title": "Первая версия",
            "description": "Полный анонс с <текстом> & символами",
            "date": "2026-11-07",
            "time": "18:00",
            "location": "Дом Москвы",
            "limit": 30,
            "points": 0,
        }
        async with self.sessions() as session:
            event_id = await save_form(
                session, self.manager, self.settings, None, "a" * 16, dict(form)
            )
        async with self.sessions() as session:
            saved = json.loads((await session.scalar(select(AppSetting).where(
                AppSetting.key == f"native-event-draft:{self.manager.id}:{'a' * 16}"
            ))).value)
            event = await session.get(Event, event_id)
            experience = await session.get(EventExperience, event_id)
            assert saved["event_id"] == event_id
            assert event.title == form["title"]
            assert event.description == form["description"]
            assert experience.creation_mode == "quick"
            assert experience.broadcast_enabled is False

        form["title"] = "Исправленная версия"
        form["limit"] = None
        async with self.sessions() as session:
            same_id = await save_form(
                session, self.manager, self.settings, None, "a" * 16, form
            )
            event_count = await session.scalar(select(func.count(Event.id)))
            event = await session.get(Event, same_id)
            assert same_id == event_id
            assert event_count == 1
            assert event.title == form["title"]
            assert event.participant_limit is None
