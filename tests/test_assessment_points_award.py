"""Assessment complete awards idempotent digital points."""

from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.assessment_service import result_payload
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

    async def test_result_payload_keeps_unlock_metadata_on_reload(self):
        session = AsyncMock()
        row = MagicMock(id=9, version_id=3, completed_at=None)
        version = MagicMock(version=1, definition_id=4, interpretation_constraints_json={})
        definition = MagicMock(code="WHO5_RU", title="Как мне сейчас?")
        session.get = AsyncMock(side_effect=[version, definition])
        session.scalars = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        payload = await result_payload(session, row)
        self.assertEqual(payload["points_awarded"], 0)
        self.assertEqual(payload["next_unlock"]["code"], "ERA_RIASEC_RU")
