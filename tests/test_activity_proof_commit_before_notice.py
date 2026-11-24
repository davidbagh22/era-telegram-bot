"""Activity proof admin notices must follow a durable commit (#529)."""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app.handlers.participant.event_activities_block15 import proof_finish
from app.utils.constants import ApplicationStatus


def _approved_user():
    return SimpleNamespace(
        id=7,
        first_name="Анна",
        last_name="ЭРА",
        application_status=ApplicationStatus.APPROVED,
        is_blocked=False,
        is_archived=False,
    )


class ActivityProofCommitBeforeNoticeTests(IsolatedAsyncioTestCase):
    async def test_proof_finish_commits_before_admin_notice(self):
        activity = SimpleNamespace(
            id=3,
            event_id=9,
            title="Фотоотчет",
            description="Сделайте фото",
            points=5,
            is_active=True,
            submission_type="text",
        )
        event = SimpleNamespace(id=9, title="Встреча")
        message = SimpleNamespace(text="Готово", caption=None, answer=AsyncMock())
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={"activity_id": 3, "proof_type": "text"}),
            clear=AsyncMock(),
        )
        session = SimpleNamespace(
            get=AsyncMock(side_effect=[activity, event]),
            scalar=AsyncMock(return_value=None),
            add=MagicMock(),
            flush=AsyncMock(),
            commit=AsyncMock(),
        )
        order: list[str] = []

        async def track_flush():
            order.append("flush")

        async def track_commit():
            order.append("commit")

        session.flush = track_flush
        session.commit = track_commit

        async def track_notify(*_args, **_kwargs):
            order.append("notify")

        with patch(
            "app.handlers.participant.event_activities_block15._notify_proof",
            new=track_notify,
        ):
            await proof_finish(
                message,
                _approved_user(),
                session,
                state,
                SimpleNamespace(),
                SimpleNamespace(),
            )

        self.assertEqual(order, ["flush", "commit", "notify"])
        state.clear.assert_awaited_once()
        message.answer.assert_awaited_once()
