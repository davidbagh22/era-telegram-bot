"""Activity callbacks reject untrusted IDs before touching PostgreSQL.

All handler paths use mocks; no real Telegram messages, registrations or points.
"""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.database.models import Event, EventActivity
from app.handlers.participant.event_activities_block15 import activities_list, proof_start
from app.handlers.participant.event_activities_block7 import activity_submit_start
from app.utils.callback_ids import positive_pg_int_callback


def _call(data):
    return SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
    )


class ActivityCallbackParserTests(TestCase):
    def test_positive_ascii_ids_preserved(self):
        for prefix in ("event:activities:", "activity:do:", "activity:submit:"):
            with self.subTest(prefix=prefix):
                self.assertEqual(positive_pg_int_callback(prefix + "42", prefix), 42)
                self.assertEqual(positive_pg_int_callback(prefix + "00042", prefix), 42)
                self.assertEqual(
                    positive_pg_int_callback(prefix + "2147483647", prefix),
                    2_147_483_647,
                )

    def test_invalid_ids_never_parse(self):
        for prefix in ("event:activities:", "activity:do:", "activity:submit:"):
            for suffix in ("", "0", "-1", "bad", "1:2", "１２", "2147483648", "9" * 5000):
                with self.subTest(prefix=prefix, suffix=suffix):
                    self.assertIsNone(positive_pg_int_callback(prefix + suffix, prefix))
            self.assertIsNone(positive_pg_int_callback(None, prefix))
            self.assertIsNone(positive_pg_int_callback("other:42", prefix))


class ActivityCallbackHandlerTests(IsolatedAsyncioTestCase):
    async def test_bad_event_activities_id_does_not_query_database(self):
        call = _call("event:activities:" + "9" * 5000)
        session = SimpleNamespace(get=AsyncMock(), scalar=AsyncMock(), scalars=AsyncMock())
        with patch("app.handlers.participant.event_activities_block15._approved", return_value=True):
            await activities_list(call, SimpleNamespace(id=1), session)
        session.get.assert_not_awaited()
        session.scalar.assert_not_awaited()
        session.scalars.assert_not_awaited()
        call.message.answer.assert_awaited_once()

    async def test_bad_activity_ids_do_not_query_or_start_proof(self):
        for prefix in ("activity:do:", "activity:submit:"):
            with self.subTest(prefix=prefix):
                call = _call(prefix + "2147483648")
                session = SimpleNamespace(get=AsyncMock(), scalar=AsyncMock())
                state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
                with patch("app.handlers.participant.event_activities_block15._approved", return_value=True):
                    await proof_start(call, SimpleNamespace(id=1), session, state,
                                      SimpleNamespace(), SimpleNamespace())
                session.get.assert_not_awaited()
                session.scalar.assert_not_awaited()
                state.set_state.assert_not_awaited()
                call.message.answer.assert_awaited_once()

    async def test_legacy_submit_router_also_rejects_bad_id(self):
        call = _call("activity:submit:" + "9" * 5000)
        session = SimpleNamespace(get=AsyncMock(), scalar=AsyncMock())
        state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
        with patch("app.handlers.participant.event_activities_block7.approved", return_value=True):
            await activity_submit_start(call, SimpleNamespace(id=1), session, state)
        session.get.assert_not_awaited()
        session.scalar.assert_not_awaited()
        state.set_state.assert_not_awaited()
        call.message.answer.assert_awaited_once()

    async def test_valid_ids_reach_existing_lookup_without_writes(self):
        call = _call("event:activities:42")
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        with patch("app.handlers.participant.event_activities_block15._approved", return_value=True):
            await activities_list(call, SimpleNamespace(id=1), session)
        session.get.assert_awaited_once_with(Event, 42)

        for prefix in ("activity:do:", "activity:submit:"):
            with self.subTest(prefix=prefix):
                call = _call(prefix + "42")
                session = SimpleNamespace(get=AsyncMock(return_value=None))
                state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
                with patch("app.handlers.participant.event_activities_block15._approved", return_value=True):
                    await proof_start(call, SimpleNamespace(id=1), session, state,
                                      SimpleNamespace(), SimpleNamespace())
                session.get.assert_awaited_once_with(EventActivity, 42)

        call = _call("activity:submit:42")
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
        with patch("app.handlers.participant.event_activities_block7.approved", return_value=True):
            await activity_submit_start(call, SimpleNamespace(id=1), session, state)
        session.get.assert_awaited_once_with(EventActivity, 42)
