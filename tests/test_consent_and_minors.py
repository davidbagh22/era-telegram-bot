from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import ConsentLog, User
from app.repositories.users import create_user_from_registration
from app.services.admin_user_card import build_admin_user_card
from app.services.consent_service import (
    CURRENT_POLICY_VERSION,
    latest_consent,
    record_consent,
)
from app.services.minors_service import is_minor


class _ScalarResult:
    def __init__(self, items: list[object]) -> None:
        self._items = items

    def all(self) -> list[object]:
        return self._items


def _card_user(**overrides) -> User:
    # Mirrors tests/test_admin_user_card.py's _user() helper: a transient
    # (never session.add()-ed) User avoids triggering a real lazy-load on
    # departments/permission_grants/etc — build_admin_user_card only needs
    # the mocked session for the handful of scalar/scalars queries below.
    data = dict(
        id=9,
        telegram_id=900,
        first_name="Тест",
        departments=[],
        directions=[],
        permission_grants=[],
    )
    data.update(overrides)
    return User(**data)


class MinorsServiceTests(unittest.TestCase):
    """Pure function — see app/services/minors_service.py docstring: this is
    a technical capability only, not a policy or enforcement decision."""

    def test_unknown_age_returns_none_not_a_boolean(self) -> None:
        self.assertIsNone(is_minor(None))

    def test_below_adult_age_is_minor(self) -> None:
        self.assertTrue(is_minor(17))

    def test_at_adult_age_is_not_minor(self) -> None:
        self.assertFalse(is_minor(18))

    def test_custom_adult_age_threshold(self) -> None:
        self.assertTrue(is_minor(20, adult_age=21))


class ConsentServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_record_consent_writes_a_row_with_current_policy_version(self) -> None:
        async with self.session_factory() as session:
            user = User(telegram_id=1, first_name="Тест")
            session.add(user)
            await session.flush()

            entry = await record_consent(
                session,
                user_id=user.id,
                consent_type="registration",
                granted=True,
                source="bot",
            )
            await session.commit()

            self.assertEqual(entry.policy_version, CURRENT_POLICY_VERSION)
            self.assertTrue(entry.granted)

    async def test_latest_consent_returns_the_most_recent_entry(self) -> None:
        async with self.session_factory() as session:
            user = User(telegram_id=2, first_name="Тест")
            session.add(user)
            await session.flush()

            await record_consent(
                session, user_id=user.id, consent_type="registration", granted=True, source="bot"
            )
            second = await record_consent(
                session, user_id=user.id, consent_type="registration", granted=False, source="miniapp"
            )
            await session.commit()

            latest = await latest_consent(session, user_id=user.id, consent_type="registration")
            self.assertEqual(latest.id, second.id)
            self.assertFalse(latest.granted)

    async def test_registration_writes_a_consent_log_row(self) -> None:
        """Confirms the wiring in app/repositories/users.py, not just that
        record_consent() works in isolation."""
        async with self.session_factory() as session:
            data = {
                "first_name": "Тест",
                "last_name": "Участник",
                "age": 20,
                "phone": "+37400000000",
                "city": "Ереван",
                "education_work": "Университет",
                "occupation": "Студент",
                "experience": "Нет",
                "motivation": "Хочу участвовать",
                "available_time": "1–2 часа в неделю",
                "desired_path": "Просто участником",
                "departments": [],
                "directions": [],
            }
            user, created = await create_user_from_registration(
                session, telegram_id=555, username="test_user", data=data
            )
            await session.commit()

            self.assertTrue(created)
            logs = (
                await session.execute(
                    ConsentLog.__table__.select().where(ConsentLog.user_id == user.id)
                )
            ).all()
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].consent_type, "registration")
            self.assertTrue(logs[0].granted)

class AdminCardMinorLabelTests(unittest.IsolatedAsyncioTestCase):
    """See tests/test_admin_user_card.py for the established mocked-session
    pattern this follows — a real, persisted User here would lazy-load
    departments/permission_grants outside the async context and fail with
    MissingGreenlet, unrelated to what these tests actually check."""

    @staticmethod
    def _mock_session() -> AsyncMock:
        session = AsyncMock()
        session.scalar.side_effect = [None, 0, 0]
        session.scalars.side_effect = [_ScalarResult([]), _ScalarResult([])]
        return session

    async def test_admin_card_shows_minor_label_for_a_minor(self) -> None:
        card = await build_admin_user_card(self._mock_session(), _card_user(age=15))
        self.assertIn("Несовершеннолетний (по анкете): да", card.text)

    async def test_admin_card_shows_not_a_minor_for_an_adult(self) -> None:
        card = await build_admin_user_card(self._mock_session(), _card_user(age=30))
        self.assertIn("Несовершеннолетний (по анкете): нет", card.text)

    async def test_admin_card_shows_unknown_when_age_not_collected(self) -> None:
        card = await build_admin_user_card(self._mock_session(), _card_user(age=None))
        self.assertIn("Несовершеннолетний (по анкете): не указано", card.text)


if __name__ == "__main__":
    unittest.main()
