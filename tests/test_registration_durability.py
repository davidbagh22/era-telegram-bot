from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import User
from app.handlers.registration import finish_registration
from app.services.consent_service import CURRENT_POLICY_VERSION
from app.utils.constants import ApplicationStatus, Role


def _registration_data() -> dict:
    return {
        "first_name": "Новый",
        "last_name": "Участник",
        "birth_date": "2000-01-01",
        "age": 26,
        "phone": "+37400000000",
        "email": "new@example.com",
        "city": "Ереван",
        "education_work": "Университет",
        "occupation": "Студент",
        "skills": ["Организация мероприятий", "SMM"],
        "experience": "Помогал организовывать студенческие и волонтёрские проекты",
        "motivation": "Хочу развиваться в ЭРА",
        "available_time": "1–2 часа в неделю",
        "desired_path": "Участник",
        "departments": [],
        "directions": [],
        "profile_photo_file_id": "telegram-photo-id",
        "social_url": "https://t.me/new_era_member",
        "consent_policy_version": CURRENT_POLICY_VERSION,
    }


def _call(telegram_id: int):
    return SimpleNamespace(
        answer=AsyncMock(),
        from_user=SimpleNamespace(id=telegram_id, username=f"user_{telegram_id}"),
        message=SimpleNamespace(answer=AsyncMock()),
    )


def _state(data: dict):
    state = AsyncMock()
    state.get_data.return_value = data
    return state


def _settings(*, admin_ids: tuple[int, ...] = ()):
    return SimpleNamespace(
        admin_ids=admin_ids,
        era_channel_url="https://t.me/era_test",
        effective_miniapp_url="https://example.test/app/",
    )


class RegistrationDurabilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_pending_registration_survives_admin_notification_failure(self) -> None:
        """A Telegram failure after submit must not roll the DB transaction back."""
        telegram_id = 880001
        state = _state(_registration_data())
        call = _call(telegram_id)
        bot = AsyncMock()

        with (
            patch(
                "app.handlers.registration.send_admin_application_cards",
                new=AsyncMock(side_effect=RuntimeError("simulated Telegram/card failure")),
            ),
            patch(
                "app.handlers.registration.admin_notification_recipients",
                new=AsyncMock(return_value={990001}),
            ),
            patch(
                "app.handlers.registration.safe_send",
                new=AsyncMock(return_value=True),
            ) as fallback_send,
        ):
            async with self.session_factory() as session:
                await finish_registration(
                    call,
                    state,
                    session,
                    bot,
                    _settings(admin_ids=(990001,)),
                )

            # Brand-new session proves the row was committed, not merely
            # visible inside the original handler transaction.
            async with self.session_factory() as verification_session:
                user = await verification_session.scalar(
                    select(User).where(User.telegram_id == telegram_id)
                )
                self.assertIsNotNone(user)
                self.assertEqual(user.application_status, ApplicationStatus.PENDING)
                self.assertEqual(user.role, Role.PARTICIPANT)
                self.assertEqual(user.skills, ["Организация мероприятий", "SMM"])
                self.assertEqual(
                    user.experience,
                    "Помогал организовывать студенческие и волонтёрские проекты",
                )

            fallback_send.assert_awaited()
            state.clear.assert_awaited_once()

    async def test_system_admin_registration_is_persisted_and_notified(self) -> None:
        """ADMIN_IDS keeps auto-approval but no longer disappears silently."""
        telegram_id = 880002
        state = _state(_registration_data())
        call = _call(telegram_id)
        bot = AsyncMock()

        with (
            patch(
                "app.handlers.registration.admin_notification_recipients",
                new=AsyncMock(return_value={telegram_id}),
            ),
            patch(
                "app.handlers.registration.safe_send",
                new=AsyncMock(return_value=True),
            ) as admin_notice,
        ):
            async with self.session_factory() as session:
                await finish_registration(
                    call,
                    state,
                    session,
                    bot,
                    _settings(admin_ids=(telegram_id,)),
                )

            async with self.session_factory() as verification_session:
                user = await verification_session.scalar(
                    select(User).where(User.telegram_id == telegram_id)
                )
                self.assertIsNotNone(user)
                self.assertEqual(user.application_status, ApplicationStatus.APPROVED)
                self.assertEqual(user.role, Role.ADMIN)

            admin_notice.assert_awaited()
            sent_text = admin_notice.await_args.args[2]
            self.assertIn("Новая регистрация ЭРА", sent_text)
            self.assertIn("автоодобрено", sent_text)


if __name__ == "__main__":
    unittest.main()
