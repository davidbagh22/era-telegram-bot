"""Regression coverage for event QR management scope.

Mock-only: no production events, Telegram sends, attendance or points.
"""
from datetime import date, time
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.handlers.participant.event_qr import _generate, qr_generate
from app.utils.constants import ApplicationStatus, Role


def _user(role=Role.LEADER, *, approved=True, blocked=False, grants=()):
    return SimpleNamespace(
        id=7,
        role=role,
        application_status=(
            ApplicationStatus.APPROVED if approved else ApplicationStatus.PENDING
        ),
        is_blocked=blocked,
        is_archived=False,
        permission_grants=list(grants),
    )


def _event(responsible_id=7):
    return SimpleNamespace(
        id=42,
        responsible_id=responsible_id,
        title="Test event",
        event_date=date(2026, 11, 1),
        event_time=time(14, 0),
        location="Test location",
    )


def _fixtures():
    message = SimpleNamespace(answer=AsyncMock())
    bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="era_1bot")))
    settings = SimpleNamespace(bot_token="0000000000:LOCALTEST")
    return message, bot, settings


class EventQrManagerScopeTests(IsolatedAsyncioTestCase):
    async def test_unassigned_leader_cannot_generate_qr(self):
        message, bot, settings = _fixtures()
        with patch(
            "app.handlers.participant.event_qr.safe_answer_photo", new_callable=AsyncMock
        ) as send:
            await _generate(message, _user(), _event(responsible_id=99), bot, settings)
        message.answer.assert_awaited_once()
        self.assertIn("нет доступа", message.answer.await_args.args[0])
        bot.get_me.assert_not_awaited()
        send.assert_not_awaited()

    async def test_generation_boundary_rejects_unapproved_or_unprivileged_user(self):
        users = (
            _user(role=Role.ADMIN, approved=False),
            _user(role=Role.ADMIN, blocked=True),
            _user(role=Role.PARTICIPANT),
        )
        for user in users:
            with self.subTest(role=user.role, status=user.application_status):
                message, bot, settings = _fixtures()
                with patch(
                    "app.handlers.participant.event_qr.safe_answer_photo",
                    new_callable=AsyncMock,
                ) as send:
                    await _generate(message, user, _event(), bot, settings)
                message.answer.assert_awaited_once()
                self.assertIn("доступен", message.answer.await_args.args[0])
                bot.get_me.assert_not_awaited()
                send.assert_not_awaited()

    async def test_assigned_leader_can_generate_qr_without_publishing(self):
        message, bot, settings = _fixtures()
        with patch(
            "app.handlers.participant.event_qr.attendance_deep_link",
            return_value="https://example.invalid/attendance",
        ) as link, patch(
            "app.handlers.participant.event_qr.qr_png", return_value=b"test-png"
        ) as qr, patch(
            "app.handlers.participant.event_qr.safe_answer_photo", new_callable=AsyncMock
        ) as send:
            await _generate(message, _user(), _event(), bot, settings)
        bot.get_me.assert_awaited_once()
        link.assert_called_once_with("era_1bot", 42, settings.bot_token)
        qr.assert_called_once_with("https://example.invalid/attendance")
        send.assert_awaited_once()
        message.answer.assert_not_awaited()

    async def test_admin_can_generate_unassigned_event_qr(self):
        message, bot, settings = _fixtures()
        with patch(
            "app.handlers.participant.event_qr.attendance_deep_link",
            return_value="https://example.invalid/attendance",
        ), patch(
            "app.handlers.participant.event_qr.qr_png", return_value=b"test-png"
        ), patch(
            "app.handlers.participant.event_qr.safe_answer_photo", new_callable=AsyncMock
        ) as send:
            await _generate(
                message, _user(role=Role.ADMIN), _event(responsible_id=99), bot, settings
            )
        send.assert_awaited_once()
        message.answer.assert_not_awaited()

    async def test_unapproved_or_blocked_admin_cannot_query_qr_callback(self):
        for user in (_user(role=Role.ADMIN, approved=False), _user(role=Role.ADMIN, blocked=True)):
            with self.subTest(user=user):
                call = SimpleNamespace(
                    data="event_qr:generate:42",
                    answer=AsyncMock(),
                    message=SimpleNamespace(answer=AsyncMock()),
                )
                session = SimpleNamespace(get=AsyncMock(), scalars=AsyncMock())
                bot = SimpleNamespace(get_me=AsyncMock())
                await qr_generate(call, user, session, bot, SimpleNamespace())
                call.answer.assert_awaited_once()
                session.get.assert_not_awaited()
                session.scalars.assert_not_awaited()
                bot.get_me.assert_not_awaited()
                call.message.answer.assert_not_awaited()
