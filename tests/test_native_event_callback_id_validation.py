"""Invalid native event callback IDs must not reach PostgreSQL or Telegram sends.

Pure parser and mocked handler paths only; no real registrations or chats.
"""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.handlers.participant.events_stability_block8 import (
    _event_id_from_callback,
    confirmation_code_start,
    event_calendar,
    event_join,
    event_view,
)


class NativeEventIdParserTests(TestCase):
    def test_valid_positive_postgres_ids(self):
        for prefix in ("event:view:", "event:join:", "event:calendar:", "event:confirm_code:"):
            with self.subTest(prefix=prefix):
                self.assertEqual(_event_id_from_callback(prefix + "00042", prefix), 42)
                self.assertEqual(_event_id_from_callback(prefix + "2147483647", prefix), 2_147_483_647)

    def test_rejects_invalid_or_oversized_ids(self):
        for prefix in ("event:view:", "event:join:", "event:calendar:", "event:confirm_code:"):
            for suffix in ("", "0", "-1", "2147483648", "bad", "1:2", "１２", "9" * 5000):
                with self.subTest(prefix=prefix, suffix=suffix):
                    self.assertIsNone(_event_id_from_callback(prefix + suffix, prefix))
            self.assertIsNone(_event_id_from_callback(None, prefix))
            self.assertIsNone(_event_id_from_callback("other:42", prefix))


class NativeEventHandlerIdTests(IsolatedAsyncioTestCase):
    async def test_bad_view_and_join_do_not_query_database(self):
        for handler, prefix in ((event_view, "event:view:"), (event_join, "event:join:")):
            with self.subTest(handler=handler.__name__):
                call = SimpleNamespace(
                    data=prefix + "2147483648",
                    answer=AsyncMock(),
                    message=SimpleNamespace(answer=AsyncMock()),
                )
                session = SimpleNamespace(get=AsyncMock(), scalar=AsyncMock())
                with patch("app.handlers.participant.events_stability_block8._approved", return_value=True):
                    await handler(call, SimpleNamespace(id=1), session)
                session.get.assert_not_awaited()
                session.scalar.assert_not_awaited()
                call.message.answer.assert_awaited_once()

    async def test_bad_calendar_does_not_query_database_or_send_document(self):
        call = SimpleNamespace(
            data="event:calendar:" + "9" * 5000,
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        session = SimpleNamespace(get=AsyncMock(), scalar=AsyncMock())
        with patch("app.handlers.participant.events_stability_block8._approved", return_value=True):
            await event_calendar(call, SimpleNamespace(id=1), session, SimpleNamespace(timezone="Asia/Yerevan"))
        session.get.assert_not_awaited()
        session.scalar.assert_not_awaited()
        call.message.answer.assert_awaited_once()

    async def test_bad_attendance_code_event_id_never_queries_database(self):
        call = SimpleNamespace(
            data="event:confirm_code:2147483648",
            from_user=SimpleNamespace(id=1),
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        session = SimpleNamespace(get=AsyncMock(), scalar=AsyncMock())
        state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
        with (
            patch("app.handlers.participant.events_stability_block8._approved", return_value=True),
            patch("app.services.event_attendance_service.attendance_v2_enabled", return_value=True),
        ):
            await confirmation_code_start(call, SimpleNamespace(id=1), SimpleNamespace(), session, state)
        session.get.assert_not_awaited()
        session.scalar.assert_not_awaited()
        state.set_state.assert_not_awaited()
        call.message.answer.assert_awaited_once()

    async def test_valid_view_reaches_existing_event_card_without_database_writes(self):
        from app.database.models import Event
        from app.utils.constants import EventStatus

        event = SimpleNamespace(id=42, status=EventStatus.PUBLISHED, participant_limit=10)
        call = SimpleNamespace(
            data="event:view:42", answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        session = SimpleNamespace(get=AsyncMock(return_value=event), scalar=AsyncMock(return_value=0))
        with (
            patch("app.handlers.participant.events_stability_block8._approved", return_value=True),
            patch("app.handlers.participant.events_stability_block8.registration_stats",
                  new_callable=AsyncMock, return_value={"free": 8, "registered": 2}),
            patch("app.handlers.participant.events_stability_block8.send_event_card",
                  new_callable=AsyncMock) as card,
        ):
            await event_view(call, SimpleNamespace(id=1), session)
        session.get.assert_awaited_once_with(Event, 42)
        card.assert_awaited_once()
        call.message.answer.assert_not_awaited()

    async def test_valid_join_preserves_already_registered_path(self):
        from app.database.models import Event
        from app.utils.constants import EventStatus

        event = SimpleNamespace(id=42, status=EventStatus.PUBLISHED)
        call = SimpleNamespace(
            data="event:join:42", answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        session = SimpleNamespace(get=AsyncMock(return_value=event))
        with (
            patch("app.handlers.participant.events_stability_block8._approved", return_value=True),
            patch("app.handlers.participant.events_stability_block8.register_for_event",
                  new_callable=AsyncMock, return_value=(None, "already")) as register,
        ):
            await event_join(call, SimpleNamespace(id=1), session)
        session.get.assert_awaited_once_with(Event, 42)
        register.assert_awaited_once_with(session, event, 1)
        call.message.answer.assert_awaited_once()

    async def test_valid_calendar_preserves_ics_delivery_path(self):
        from app.database.event_experience import EventExperience
        from app.database.models import Event
        from app.utils.constants import EventStatus

        event = SimpleNamespace(id=42, status=EventStatus.PUBLISHED)
        call = SimpleNamespace(
            data="event:calendar:42", answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        session = SimpleNamespace(
            get=AsyncMock(side_effect=[event, None]),
            scalar=AsyncMock(return_value=None),
        )
        with (
            patch("app.handlers.participant.events_stability_block8._approved", return_value=True),
            patch("app.services.event_calendar_service.build_event_calendar",
                  return_value=b"BEGIN:VCALENDAR\nEND:VCALENDAR") as build,
            patch("app.handlers.participant.events_stability_block8.safe_answer_document",
                  new_callable=AsyncMock) as deliver,
        ):
            await event_calendar(call, SimpleNamespace(id=1), session,
                                 SimpleNamespace(timezone="Asia/Yerevan"))
        self.assertEqual(session.get.await_args_list[0].args, (Event, 42))
        self.assertEqual(session.get.await_args_list[1].args, (EventExperience, 42))
        build.assert_called_once()
        deliver.assert_awaited_once()
        call.message.answer.assert_not_awaited()

    async def test_valid_confirmation_code_stores_exact_event_id(self):
        call = SimpleNamespace(
            data="event:confirm_code:42",
            from_user=SimpleNamespace(id=1),
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        session = SimpleNamespace()
        state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
        with (
            patch("app.handlers.participant.events_stability_block8._approved", return_value=True),
            patch("app.services.event_attendance_service.attendance_v2_enabled", return_value=True),
            patch("app.services.event_attendance_service.participant_state",
                  new_callable=AsyncMock,
                  return_value=SimpleNamespace(confirmation_open=True)) as participant,
        ):
            await confirmation_code_start(call, SimpleNamespace(id=1),
                                          SimpleNamespace(), session, state)
        participant.assert_awaited_once_with(session, 42, 1)
        state.set_state.assert_awaited_once()
        state.update_data.assert_awaited_once_with(attendance_event_id=42)
        call.message.answer.assert_awaited_once()
