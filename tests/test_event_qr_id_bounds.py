"""Bound QR event IDs before any database query or QR generation.

Mock-only; no Telegram messages, real events, attendance, or points.
"""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.database.models import Event
from app.handlers.participant.event_qr import qr_command, qr_generate


class QrEventIdBoundsTests(IsolatedAsyncioTestCase):
    async def test_invalid_qr_command_never_queries_database(self):
        for raw in ("0", "-1", "bad", "2147483648", "１２", "42 extra", "9" * 5000):
            with self.subTest(raw=raw[:20]):
                message = SimpleNamespace(answer=AsyncMock())
                session = SimpleNamespace(get=AsyncMock(), scalars=AsyncMock())
                with patch("app.handlers.participant.event_qr._approved", return_value=True), patch(
                    "app.handlers.participant.event_qr._can_manage_qr", return_value=True
                ):
                    await qr_command(
                        message, SimpleNamespace(args=raw), SimpleNamespace(id=1),
                        session, SimpleNamespace(), SimpleNamespace(),
                    )
                session.get.assert_not_awaited()
                session.scalars.assert_not_awaited()
                message.answer.assert_awaited_once()

    async def test_valid_qr_command_preserves_lookup(self):
        message = SimpleNamespace(answer=AsyncMock())
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        with patch("app.handlers.participant.event_qr._approved", return_value=True), patch(
            "app.handlers.participant.event_qr._can_manage_qr", return_value=True
        ):
            await qr_command(
                message, SimpleNamespace(args=" 42 "), SimpleNamespace(id=1),
                session, SimpleNamespace(), SimpleNamespace(),
            )
        session.get.assert_awaited_once_with(Event, 42)
        message.answer.assert_awaited_once()

    async def test_invalid_qr_callback_never_queries_database(self):
        for suffix in ("", "0", "-1", "bad", "2147483648", "９", "9" * 5000):
            with self.subTest(suffix=suffix[:20]):
                call = SimpleNamespace(
                    data="event_qr:generate:" + suffix,
                    answer=AsyncMock(),
                    message=SimpleNamespace(answer=AsyncMock()),
                )
                session = SimpleNamespace(get=AsyncMock())
                with patch("app.handlers.participant.event_qr._approved", return_value=True), patch(
                    "app.handlers.participant.event_qr._can_manage_qr", return_value=True
                ):
                    await qr_generate(
                        call, SimpleNamespace(id=1), session,
                        SimpleNamespace(), SimpleNamespace(),
                    )
                call.answer.assert_awaited_once()
                session.get.assert_not_awaited()

    async def test_valid_qr_callback_preserves_lookup(self):
        call = SimpleNamespace(
            data="event_qr:generate:42", answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        with patch("app.handlers.participant.event_qr._approved", return_value=True), patch(
            "app.handlers.participant.event_qr._can_manage_qr", return_value=True
        ):
            await qr_generate(
                call, SimpleNamespace(id=1), session,
                SimpleNamespace(), SimpleNamespace(),
            )
        session.get.assert_awaited_once_with(Event, 42)
        call.message.answer.assert_awaited_once()
