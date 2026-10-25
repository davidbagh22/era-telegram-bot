"""Regression tests for the 2026-08 System Flow Audit (docs/SYSTEM_FLOW_MATRIX.md).

Pins the real, behavioral fix — not just a string match on source code — for
the "leader_approved submissions look unsubmitted" bug found at three call
sites: cabinet.py::my_events, event_plans_changed.py::my_events, and the
*live* event_activities_block15.py::proof_start (event_activities_block7.py's
near-identical handler never actually runs — see the audit doc for why).

Each test drives the real handler against a real SQLite DB (no mocked SQL),
so a regression to the old hand-rolled ["pending", "approved"] filter would
make these fail for the real reason: the activity re-appears as submittable,
or the duplicate-submit guard silently lets a second submission through.
"""
from __future__ import annotations

import unittest
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import (
    Event,
    EventActivity,
    EventActivitySubmission,
    EventRegistration,
    User,
)
from app.handlers.participant import cabinet, event_activities_block15, event_plans_changed
from app.utils.constants import ApplicationStatus, EventStatus, RegistrationStatus


class _CallStub(SimpleNamespace):
    def __init__(self, data: str = "") -> None:
        super().__init__(
            data=data,
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )


class LeaderApprovedNotTreatedAsUnsubmittedTests(unittest.IsolatedAsyncioTestCase):
    """A submission at 'leader_approved' must count as 'already submitted' —
    it is a real, live intermediate status between a leader's pre-approval
    and the admin's final sign-off (see event_activity_service.REVIEWABLE_STATUSES),
    not a resting/idle state."""

    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _seed(self, session):
        user = User(
            telegram_id=900001,
            first_name="Тест",
            application_status=ApplicationStatus.APPROVED,
        )
        session.add(user)
        await session.flush()
        event = Event(
            title="Митап",
            description="d",
            event_date=date(2026, 1, 1),
            event_time=time(18, 0),
            location="Онлайн",
            format="online",
            status=EventStatus.COMPLETED,
            created_by=user.id,
        )
        session.add(event)
        await session.flush()
        registration = EventRegistration(
            event_id=event.id, user_id=user.id, status=RegistrationStatus.ATTENDED
        )
        activity = EventActivity(
            event_id=event.id, title="Отзыв", description="d", submission_type="text", points=10, is_active=True
        )
        session.add_all([registration, activity])
        await session.flush()
        submission = EventActivitySubmission(
            activity_id=activity.id, user_id=user.id, status="leader_approved", text="ок"
        )
        session.add(submission)
        await session.flush()
        return user, event, activity

    async def test_cabinet_my_events_hides_leader_approved_activity(self) -> None:
        async with self.session_factory() as session:
            user, event, activity = await self._seed(session)
            call = _CallStub()
            await cabinet.my_events(call, user, session)
            text, kwargs = call.message.answer.call_args
            keyboard = kwargs["reply_markup"].inline_keyboard
            offered_callbacks = {btn.callback_data for row in keyboard for btn in row}
            self.assertNotIn(
                f"event:activity:{activity.id}",
                offered_callbacks,
                "leader_approved submission was offered again for a duplicate submit",
            )

    async def test_event_plans_changed_my_events_hides_leader_approved_activity(self) -> None:
        async with self.session_factory() as session:
            user, event, activity = await self._seed(session)
            call = _CallStub(data="cabinet:events")
            await event_plans_changed.my_events(call, user, session)
            text, kwargs = call.message.answer.call_args
            keyboard = kwargs["reply_markup"].inline_keyboard
            offered_callbacks = {btn.callback_data for row in keyboard for btn in row}
            self.assertNotIn(
                f"event:activity:{activity.id}",
                offered_callbacks,
                "leader_approved submission was offered again for a duplicate submit",
            )

    async def test_proof_start_blocks_resubmission_while_leader_approved(self) -> None:
        # This is the handler that actually runs for activity:submit:* traffic
        # (registered before event_activities_block7.py's dead duplicate —
        # see docs/SYSTEM_FLOW_MATRIX.md).
        async with self.session_factory() as session:
            user, event, activity = await self._seed(session)
            call = _CallStub(data=f"activity:submit:{activity.id}")
            state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
            bot = SimpleNamespace()
            settings = SimpleNamespace()
            await event_activities_block15.proof_start(call, user, session, state, bot, settings)
            state.set_state.assert_not_awaited()
            call.message.answer.assert_awaited_once()
            (message_text,), _ = call.message.answer.call_args
            self.assertIn("уже на проверке", message_text)


if __name__ == "__main__":
    unittest.main()
