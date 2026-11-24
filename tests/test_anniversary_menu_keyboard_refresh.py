"""After anniversary RSVP the reply keyboard must switch to the ticket label."""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import Settings
from app.handlers import anniversary as handler
from app.services import anniversary_registration_service as rsvp
from app.utils.constants import ApplicationStatus, Role


class AnniversaryMenuKeyboardRefreshTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=11, user_id=11))
        self.settings = Settings(
            bot_token="1234567890:test",
            miniapp_auth_secret="test",
            miniapp_url="https://era.example/app/",
        )
        self.user = SimpleNamespace(
            id=1,
            telegram_id=11,
            role=Role.PARTICIPANT,
            application_status=ApplicationStatus.APPROVED,
            is_blocked=False,
            is_archived=False,
            first_name="Анна",
            last_name="Иванова",
            education_work="ЭРА",
            office_assignments=[],
        )
        self.message = SimpleNamespace(
            from_user=SimpleNamespace(id=11),
            answer=AsyncMock(),
        )
        self.guest = {
            "first_name": "Анна",
            "last_name": "Иванова",
            "organization": "ЭРА",
            "telegram_id": 11,
            "registered_at": "2026-11-18T12:00:00+04:00",
        }

    async def test_fresh_rsvp_attaches_ticket_reply_keyboard(self):
        event = SimpleNamespace(id=7)
        with (
            patch.object(rsvp, "featured_event", AsyncMock(return_value=event)),
            patch.object(rsvp, "check_event_registration", AsyncMock(return_value=False)),
            patch.object(rsvp, "register", AsyncMock(return_value=self.guest)),
            patch.object(rsvp, "menu_available", AsyncMock(return_value=True)),
            patch.object(rsvp, "profile_defaults", return_value={
                "first_name": "Анна", "last_name": "Иванова", "organization": "ЭРА",
            }),
        ):
            await handler.menu_registration(
                self.message, self.state, session=AsyncMock(), user=self.user, settings=self.settings,
            )
        kwargs = self.message.answer.await_args.kwargs
        labels = {button.text for row in kwargs["reply_markup"].keyboard for button in row}
        assert rsvp.MENU_TICKET_BUTTON in labels
        assert rsvp.MENU_BUTTON not in labels
        assert "Вы зарегистрированы" in self.message.answer.await_args.args[0]

    async def test_ticket_tap_shows_existing_details_without_reregister_copy(self):
        event = SimpleNamespace(id=7)
        with (
            patch.object(rsvp, "featured_event", AsyncMock(return_value=event)),
            patch.object(rsvp, "check_event_registration", AsyncMock(return_value=True)),
            patch.object(rsvp, "get_registration", AsyncMock(return_value=self.guest)),
            patch.object(rsvp, "menu_available", AsyncMock(return_value=True)),
        ):
            await handler.menu_registration(
                self.message, self.state, session=AsyncMock(), user=self.user, settings=self.settings,
            )
        text = self.message.answer.await_args.args[0]
        assert "уже в списке" in text
        assert "Анна" in text
        assert "Зарегистрироваться" not in text
        labels = {
            button.text
            for row in self.message.answer.await_args.kwargs["reply_markup"].keyboard
            for button in row
        }
        assert rsvp.MENU_TICKET_BUTTON in labels
