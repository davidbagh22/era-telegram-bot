"""POST /api/v1/leadership/nominations — participant suggests leadership."""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.v1.leadership import NominationIn, nominate_leader
from app.utils.constants import ApplicationStatus


class LeadershipNominationTests(IsolatedAsyncioTestCase):
    async def test_rejects_short_reason_and_unknown_nominee(self):
        user = SimpleNamespace(id=1, first_name="Ann", last_name=None, application_status=ApplicationStatus.APPROVED)
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        with self.assertRaises(HTTPException) as missing:
            await nominate_leader(
                NominationIn(nominee_user_id=99, reason="Готов вести направление"),
                user=user,
                session=session,
                bot=None,
                settings=SimpleNamespace(effective_miniapp_url=""),
            )
        self.assertEqual(missing.exception.status_code, 404)

    async def test_notifies_admins_for_valid_nomination(self):
        user = SimpleNamespace(id=1, first_name="Ann", last_name=None, application_status=ApplicationStatus.APPROVED)
        nominee = SimpleNamespace(id=2, first_name="Bob", last_name="Lee", application_status=ApplicationStatus.APPROVED)
        session = AsyncMock()
        session.get = AsyncMock(return_value=nominee)
        bot = object()
        settings = SimpleNamespace(effective_miniapp_url="https://era.example/app/")
        with patch("app.api.v1.leadership.notify_admins_once", new_callable=AsyncMock) as notify:
            result = await nominate_leader(
                NominationIn(nominee_user_id=2, reason="Сильный лидер команды медиа"),
                user=user,
                session=session,
                bot=bot,
                settings=settings,
            )
        self.assertTrue(result.ok)
        notify.assert_awaited()
        key = notify.await_args.kwargs["delivery_key"]
        self.assertTrue(key.startswith("admin:leader_nomination:1:2:"))
        self.assertEqual(len(key.rsplit(":", 1)[-1]), 32)
