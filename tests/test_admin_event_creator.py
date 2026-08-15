from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.api.v1.admin_event_create import AdminEventCreateIn, create_event_from_admin
from app.utils.constants import EventStatus


class AdminEventCreatorTests(unittest.TestCase):
    def test_publish_path_creates_registration_open_event_and_commits(self) -> None:
        session = SimpleNamespace(add=Mock(), flush=AsyncMock(), commit=AsyncMock())

        async def assign_id() -> None:
            event = session.add.call_args.args[0]
            event.id = 91

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

        event = session.add.call_args.args[0]
        self.assertEqual(event.created_by, 7)
        self.assertEqual(event.approved_by, 7)
        self.assertEqual(event.status, EventStatus.REGISTRATION_OPEN)
        self.assertEqual(result.id, 91)
        self.assertEqual(result.status, EventStatus.REGISTRATION_OPEN)
        session.commit.assert_awaited_once()
        audit_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
