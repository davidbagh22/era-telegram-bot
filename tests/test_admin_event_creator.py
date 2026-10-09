from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.api.v1.admin_event_create import (
    AdminEventCreateIn,
    _ensure_publish_description,
    _validate_publish,
    create_event_from_admin,
)
from app.database.event_experience import EventExperience
from app.database.models import Event
from app.utils.constants import EventStatus


class AdminEventCreatorTests(unittest.TestCase):
    def test_publish_uses_short_description_when_long_description_missing(self) -> None:
        event = SimpleNamespace(title="Что? Где? Когда?", description="", location="Дом Москвы")
        experience = SimpleNamespace(short_description="Игра про космос", full_description="")
        _ensure_publish_description(event, experience)
        self.assertEqual(experience.full_description, "Игра про космос")
        self.assertEqual(event.description, "Игра про космос")
        self.assertEqual(_validate_publish(event, experience), [])

    def test_publish_rejects_event_without_any_description(self) -> None:
        event = SimpleNamespace(title="Что? Где? Когда?", description="", location="Дом Москвы")
        experience = SimpleNamespace(short_description="", full_description="")
        _ensure_publish_description(event, experience)
        self.assertIn("full_description", _validate_publish(event, experience))

    def test_publish_keeps_existing_long_description(self) -> None:
        event = SimpleNamespace(title="Что? Где? Когда?", description="", location="Дом Москвы")
        experience = SimpleNamespace(short_description="Кратко", full_description="Полная программа игры")
        _ensure_publish_description(event, experience)
        self.assertEqual(event.description, "Полная программа игры")

    def test_publish_path_creates_registration_open_event_and_companion_data(self) -> None:
        session = SimpleNamespace(add=Mock(), flush=AsyncMock(), commit=AsyncMock())

        async def assign_id() -> None:
            first_added = session.add.call_args_list[0].args[0]
            first_added.id = 91

        session.flush.side_effect = assign_id
        payload = AdminEventCreateIn(
            title="Медиа без скуки",
            description="Практическая встреча с понятным результатом для участника.",
            event_date="2026-09-01",
            event_time="18:30",
            location="Дом Москвы",
            format="Мастер-класс",
            participant_limit=30,
            points_for_visit=5,
            needs_volunteers=True,
            publish=True,
        )

        with patch("app.api.v1.admin_event_create.audit", new=AsyncMock()) as audit_mock:
            result = asyncio.run(
                create_event_from_admin(payload, admin=SimpleNamespace(id=7), session=session)
            )

        added = [call.args[0] for call in session.add.call_args_list]
        event = next(item for item in added if isinstance(item, Event))
        experience = next(item for item in added if isinstance(item, EventExperience))
        self.assertEqual(event.created_by, 7)
        self.assertEqual(event.approved_by, 7)
        self.assertEqual(event.status, EventStatus.REGISTRATION_OPEN)
        self.assertEqual(experience.event_id, 91)
        self.assertTrue(experience.is_complete)
        self.assertEqual(result.id, 91)
        self.assertEqual(result.status, EventStatus.REGISTRATION_OPEN)
        # Request-scoped get_session commits successful API writes centrally.
        session.commit.assert_not_awaited()
        audit_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
