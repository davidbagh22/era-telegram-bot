"""Short bot menu: two persistent reply buttons, everything else inline,
and every legacy reply-button text / command keeps working."""

from __future__ import annotations

import os
import unittest
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.types import Chat, Message, User as TgUser
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import Event, EventRegistration, User
from app.keyboards.bot_shell import (
    HELP_BUTTON_ALIASES,
    LEGACY_REPLY_BUTTON_TEXTS,
    admin_hub_keyboard,
    help_hub_keyboard,
    main_reply_keyboard,
)
from app.services.anniversary_registration_service import MENU_BUTTON, MENU_TICKET_BUTTON
from app.utils.constants import ApplicationStatus, Role

URL = "https://era.example/app/"


def _reply_texts(markup) -> list[str]:
    return [button.text for row in markup.keyboard for button in row]


def _inline(markup):
    return [button for row in markup.inline_keyboard for button in row]


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"admin": True},
        {"leaders": True},
        {"media_chair": True},
        {"anniversary": True},
        {"anniversary": True, "anniversary_registered": True},
        {"admin": True, "leaders": True, "media_chair": True, "anniversary": True},
    ],
)
@pytest.mark.parametrize("url", ["", URL])
def test_persistent_reply_keyboard_has_exactly_two_buttons(url, kwargs):
    markup = main_reply_keyboard(url, **kwargs)
    assert _reply_texts(markup) == ["🔥 Открыть ЭРА", "❓ Помощь"]
    assert markup.is_persistent and markup.one_time_keyboard is False
    assert all(button.web_app is None for row in markup.keyboard for button in row)


def test_help_hub_keeps_every_old_reply_entry_as_inline_buttons():
    participant = {b.callback_data for b in _inline(help_hub_keyboard(URL))}
    assert {"events:list", "cabinet:open", "offers:menu", "contact:menu", "faq:home", "nav:guide"} <= participant
    assert "wc:home" not in participant and "admin:hub:open" not in participant

    roles = _inline(help_hub_keyboard(URL, admin=True, leaders=True, media_chair=True))
    assert {"wc:home", "media:leader", "admin:hub:open"} <= {b.callback_data for b in roles}

    open_label = {b.text for b in _inline(help_hub_keyboard(URL, anniversary=True))}
    ticket_label = {b.text for b in _inline(help_hub_keyboard(URL, anniversary=True, anniversary_registered=True))}
    assert MENU_BUTTON in open_label and MENU_TICKET_BUTTON not in open_label
    assert MENU_TICKET_BUTTON in ticket_label and MENU_BUTTON not in ticket_label
    assert "anniversary:menu" in {b.callback_data for b in _inline(help_hub_keyboard(URL, anniversary=True))}


def test_admin_hub_has_three_primary_actions_and_more():
    buttons = _inline(admin_hub_keyboard(URL, pending=4))
    assert [b.text for b in buttons] == ["🎉 Мероприятия", "📥 Заявки · 4", "✅ Задачи", "⋯ Ещё"]
    assert buttons[0].web_app and "adminSection=events" in buttons[0].web_app.url
    assert [b.callback_data for b in buttons[1:]] == ["admin:applications", "admin:tasks", "admin:hub:more"]
    assert [b.text for b in _inline(admin_hub_keyboard(URL))][1] == "📥 Заявки"
    assert [b.text for b in _inline(admin_hub_keyboard(URL, pending=0))][1] == "📥 Заявки"


def test_admin_hub_more_keeps_all_previous_tools():
    more = _inline(admin_hub_keyboard(URL, expanded=True))
    callbacks = {b.callback_data for b in more}
    assert {"admin:management:open", "menu:main", "admin:hub:home"} <= callbacks
    assert any(b.web_app and b.text == "⚙️ Управление ЭРА" for b in more)
    assert "admin:applications" not in callbacks


_DISPATCHER = None


def _dispatcher():
    global _DISPATCHER
    if _DISPATCHER is None:
        os.environ["FSM_STORAGE_MODE"] = "memory"
        from app.bot import create_dispatcher

        _DISPATCHER = create_dispatcher(Settings(bot_token="1234567890:test-token"), None)
    return _DISPATCHER


def _walk(router):
    yield router
    for sub in router.sub_routers:
        yield from _walk(sub)


async def _first_handler(dispatcher, text: str, *, raw_state: str | None = None) -> str | None:
    message = Message(
        message_id=1, date=datetime.now(), chat=Chat(id=5, type="private"),
        from_user=TgUser(id=5, is_bot=False, first_name="x"), text=text,
    )
    bot = Bot("1234567890:test-token")
    try:
        for router in _walk(dispatcher):
            for handler in router.message.handlers:
                try:
                    matched, _ = await handler.check(
                        message, raw_state=raw_state, bot=bot, event_chat=message.chat,
                        event_from_user=message.from_user,
                    )
                except Exception:
                    matched = False
                if matched:
                    return f"{router.name}:{handler.callback.__name__}"
    finally:
        await bot.session.close()
    return None


class ShortBotMenuRoutingTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def tearDownClass(cls):
        global _DISPATCHER
        if _DISPATCHER is not None:
            for sub in list(_DISPATCHER.sub_routers):
                sub._parent_router = None
            _DISPATCHER.sub_routers.clear()
            _DISPATCHER = None
        super().tearDownClass()

    async def test_every_legacy_reply_button_text_still_routes_to_a_handler(self):
        unrouted = [text for text in sorted(LEGACY_REPLY_BUTTON_TEXTS) if await _first_handler(_dispatcher(), text) is None]
        assert unrouted == []


    async def test_legacy_texts_keep_their_original_handlers(self):
        expected = {
            "📅 Афиша": "emergency_navigation:rescue_menu_button",
            "📅 Мероприятия": "participant_events_stability_block8:event_list_button",
            "🌱 Мой путь": "cabinet:journey_button",
            "⭐ Возможности": "emergency_navigation:rescue_menu_button",
            "💬 Связь": "emergency_navigation:rescue_menu_button",
            "🔥 Открыть ЭРА": "emergency_navigation:rescue_menu_button",
            "🧭 Лидеры": "leaders_native:native_leaders",
            "🎬 Медиа": "media_management:leader_command",
            "⚙️ Админ": "admin_commands_ready:admin_hub_command",
            "🎟 Зарегистрироваться на годовщину": "anniversary:menu_registration",
            "🎟 Годовщина · я в списке": "anniversary:menu_registration",
        }
        for text, handler in expected.items():
            assert await _first_handler(_dispatcher(), text) == handler, text


    async def test_help_button_texts_route_to_help_hub(self):
        for text in sorted(HELP_BUTTON_ALIASES):
            assert await _first_handler(_dispatcher(), text) == "emergency_navigation:rescue_help_button", text


    async def test_persistent_buttons_escape_active_fsm_forms(self):
        from app.handlers.anniversary import AnniversaryStates
        from app.handlers.book_club import ReflectionStates
        from app.handlers.emergency import rescue_help_button
        from app.handlers.leader.events_block6 import EventBlock6States
        from app.handlers.pulse_private import PulseState

        active_states = [
            AnniversaryStates.first_name.state,
            AnniversaryStates.last_name.state,
            AnniversaryStates.organization.state,
            PulseState.answer.state,
            ReflectionStates.answer.state,
            EventBlock6States.date.state,
        ]
        for active_state in active_states:
            for text in sorted(HELP_BUTTON_ALIASES):
                assert (
                    await _first_handler(_dispatcher(), text, raw_state=active_state)
                    == "emergency_navigation:rescue_help_button"
                ), (active_state, text)
            assert (
                await _first_handler(_dispatcher(), "🔥 Открыть ЭРА", raw_state=active_state)
                == "emergency_navigation:rescue_menu_button"
            ), active_state

        assert (
            await _first_handler(_dispatcher(), "Иван", raw_state=AnniversaryStates.first_name.state)
            == "anniversary:field"
        )

        state = SimpleNamespace(clear=AsyncMock())
        user = SimpleNamespace(
            telegram_id=1, role=Role.PARTICIPANT, application_status=ApplicationStatus.APPROVED,
            is_blocked=False, is_archived=False, office_assignments=[],
        )
        settings = Settings(bot_token="1234567890:test-token", miniapp_url=URL)
        message = SimpleNamespace(answer=AsyncMock())
        await rescue_help_button(message, user, settings, state, None)
        state.clear.assert_awaited_once()
        assert "events:list" in {b.callback_data for b in _inline(message.answer.await_args.kwargs["reply_markup"])}


    async def test_existing_commands_still_routed(self):
        for command in (
            "/start", "/help", "/menu", "/navigation", "/contact", "/events", "/tasks", "/profile",
            "/opportunities", "/points", "/journey", "/cancel", "/report", "/games", "/play",
        ):
            assert await _first_handler(_dispatcher(), command) is not None, command
        assert await _first_handler(_dispatcher(), "/help") == "participant_commands_ready:help_command"


    async def test_send_help_hub_uses_role_entries_and_blocks_unapproved(self):
        from app.handlers.participant.navigation import send_help_hub

        admin = SimpleNamespace(
            telegram_id=1, role=Role.ADMIN, application_status=ApplicationStatus.APPROVED,
            is_blocked=False, is_archived=False, office_assignments=[],
        )
        settings = Settings(bot_token="1234567890:test-token", miniapp_url=URL)
        message = SimpleNamespace(answer=AsyncMock())
        await send_help_hub(message, admin, settings, None)
        markup = message.answer.await_args.kwargs["reply_markup"]
        assert "admin:hub:open" in {b.callback_data for b in _inline(markup)}

        pending = SimpleNamespace(**{**admin.__dict__, "application_status": ApplicationStatus.PENDING, "role": Role.PARTICIPANT})
        message = SimpleNamespace(answer=AsyncMock())
        await send_help_hub(message, pending, settings, None)
        assert "reply_markup" not in message.answer.await_args.kwargs


    async def test_admin_hub_text_shows_pending_count_and_latest_registration(self):
        from app.handlers.admin.commands_ready import admin_hub_text

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                def person(tid, **kw):
                    return User(
                        telegram_id=tid, first_name=kw.pop("first_name", f"U{tid}"), phone="+1", city="c",
                        education_work="w", occupation="o", motivation="m", available_time="a",
                        desired_path="participant", personal_data_consent=True, is_channel_subscribed=True, **kw,
                    )
                organizer = person(1, role=Role.ADMIN, application_status=ApplicationStatus.APPROVED)
                waiting = person(2, application_status=ApplicationStatus.PENDING)
                guest = person(3, first_name="Мария", application_status=ApplicationStatus.APPROVED)
                session.add_all([organizer, waiting, guest])
                await session.flush()
                event = Event(title="Вечер <ЭРА>", description="d", event_date=date(2026, 12, 1), event_time=time(18, 0),
                              location="x", format="offline", status="published", created_by=organizer.id)
                session.add(event)
                await session.flush()
                session.add(EventRegistration(
                    event_id=event.id, user_id=guest.id, status="registered",
                    created_at=datetime(2026, 11, 20, 8, 5, tzinfo=timezone.utc),
                ))
                await session.commit()
                text, pending = await admin_hub_text(session, Settings(bot_token="1234567890:test-token"))
            self.assertEqual(pending, 1)
            assert "Заявок на рассмотрении: <b>1</b>" in text
            assert "Мария — Вечер &lt;ЭРА&gt;" in text
            assert "20.11 12:05" in text
        finally:
            await engine.dispose()
