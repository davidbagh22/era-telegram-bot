from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.progression_service import promote_participation_status
from app.utils.constants import ParticipationStatus


class ReferralProgressionHookTests(unittest.IsolatedAsyncioTestCase):
    async def test_crossing_active_status_awards_referral_milestone(self) -> None:
        user = SimpleNamespace(
            id=77,
            participation_status=ParticipationStatus.INVOLVED_MEMBER,
        )
        session = SimpleNamespace(
            get=AsyncMock(return_value=user),
            flush=AsyncMock(),
        )

        with (
            patch(
                "app.services.progression_service.get_all_metrics",
                new=AsyncMock(return_value={"events_attended": 3}),
            ),
            patch(
                "app.services.progression_service.audit",
                new=AsyncMock(),
            ),
            patch(
                "app.services.referral_service.award_active_referral",
                new=AsyncMock(),
            ) as award_mock,
        ):
            result = await promote_participation_status(session, user_id=user.id)

        self.assertEqual(result, str(ParticipationStatus.ACTIVE_MEMBER))
        award_mock.assert_awaited_once_with(session, invitee_user_id=user.id)
