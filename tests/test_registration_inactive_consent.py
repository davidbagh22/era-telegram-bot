"""Regression: stale registration consent must never revive inactive users.

Uses mocks only: no database writes, Telegram sends or production identities.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers.registration import finish_registration
from app.services.consent_service import CURRENT_POLICY_VERSION


def test_inactive_user_cannot_finish_stale_registration_consent() -> None:
    for blocked, archived in ((True, False), (False, True)):
        existing = SimpleNamespace(is_blocked=blocked, is_archived=archived)
        call = SimpleNamespace(
            from_user=SimpleNamespace(id=7),
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={
                "consent_policy_version": CURRENT_POLICY_VERSION,
            }),
            clear=AsyncMock(),
        )
        session = SimpleNamespace(scalar=AsyncMock(return_value=existing), commit=AsyncMock())
        with (
            patch("app.handlers.registration._ensure_complete", new=AsyncMock(return_value=True)),
            patch("app.handlers.registration.create_user_from_registration", new=AsyncMock()) as create,
            patch("app.handlers.registration.resubmit_user_registration", new=AsyncMock()) as resubmit,
        ):
            asyncio.run(finish_registration(
                call, state, session, object(), SimpleNamespace(admin_ids=[7])
            ))
            create.assert_not_awaited()
            resubmit.assert_not_awaited()
        call.answer.assert_awaited_once()
        session.scalar.assert_awaited_once()
        session.commit.assert_not_awaited()
        state.clear.assert_awaited_once()
        call.message.answer.assert_awaited_once()
        assert "Регистрация недоступна" in call.message.answer.await_args.args[0]
