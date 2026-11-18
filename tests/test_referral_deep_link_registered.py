"""Registered users hitting a dead invite link land on home, not registration copy."""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import Settings
from app.handlers.referrals import referral_deep_link
from app.utils.constants import ApplicationStatus, Role


class ReferralDeepLinkRegisteredTests(IsolatedAsyncioTestCase):
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
            office_assignments=[],
        )
        self.message = SimpleNamespace(
            from_user=SimpleNamespace(id=11),
            answer=AsyncMock(),
            bot=SimpleNamespace(),
        )
        self.command = SimpleNamespace(args="ref_000000")

    async def test_invalid_code_for_registered_user_opens_home(self):
        with (
            patch(
                "app.handlers.referrals.validate_referral_code",
                AsyncMock(side_effect=ValueError("missing")),
            ),
            patch("app.handlers.start.show_home", AsyncMock()) as show_home,
            patch(
                "app.handlers.start.anniversary.menu_available",
                AsyncMock(return_value=False),
            ),
        ):
            await referral_deep_link(
                self.message,
                self.command,
                self.state,
                session=AsyncMock(),
                user=self.user,
                settings=self.settings,
            )
        self.message.answer.assert_awaited()
        text = self.message.answer.await_args.args[0]
        assert "уже в ЭРА" in text
        assert "регистрацию через /start" not in text
        show_home.assert_awaited()

    async def test_valid_code_for_registered_user_still_opens_home(self):
        code_row = SimpleNamespace(code="123456")
        with (
            patch(
                "app.handlers.referrals.validate_referral_code",
                AsyncMock(return_value=(code_row, SimpleNamespace())),
            ),
            patch("app.handlers.start.show_home", AsyncMock()) as show_home,
        ):
            await referral_deep_link(
                self.message,
                self.command,
                self.state,
                session=AsyncMock(),
                user=self.user,
                settings=self.settings,
            )
        text = self.message.answer.await_args.args[0]
        assert "уже зарегистрированы" in text
        show_home.assert_awaited()

    async def test_referral_start_callback_for_registered_user_opens_home(self):
        from app.handlers.referrals import registration_start_with_referral

        call = SimpleNamespace(
            data="registration:ref:start:123456",
            from_user=SimpleNamespace(id=11),
            answer=AsyncMock(),
            message=self.message,
        )
        with (
            patch(
                "app.handlers.referrals.validate_referral_code",
                AsyncMock(return_value=(SimpleNamespace(code="123456"), SimpleNamespace())),
            ),
            patch("app.handlers.start.show_home", AsyncMock()) as show_home,
            patch("app.handlers.referrals._begin_registration", AsyncMock()) as begin_registration,
            patch(
                "app.handlers.referrals.offer_registration_resume",
                AsyncMock(return_value=False),
            ) as offer_resume,
        ):
            await registration_start_with_referral(
                call,
                self.state,
                session=AsyncMock(),
                bot=AsyncMock(),
                settings=self.settings,
                user=self.user,
            )
        call.answer.assert_awaited()
        text = self.message.answer.await_args.args[0]
        assert "уже в ЭРА" in text
        assert "регистрацию через /start" not in text
        show_home.assert_awaited()
        begin_registration.assert_not_awaited()
        offer_resume.assert_not_awaited()
