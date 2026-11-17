"""Assessment complete awards idempotent digital points."""

from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.digital_engagement_service import award_assessment_complete


class AssessmentPointsAwardTests(IsolatedAsyncioTestCase):
    async def test_award_assessment_complete_is_idempotent_by_session(self):
        session = AsyncMock()
        with patch(
            "app.services.digital_engagement_service._award_digital",
            new_callable=AsyncMock,
        ) as award:
            award.return_value = MagicMock(points=25)
            tx = await award_assessment_complete(
                session, user_id=7, assessment_code="WHO5_RU", session_id=42
            )
        self.assertEqual(tx.points, 25)
        award.assert_awaited_once()
        kwargs = award.await_args.kwargs
        self.assertEqual(kwargs["idempotency_key"], "digital:assessment:7:WHO5_RU:42")
        self.assertEqual(kwargs["points"], 25)
