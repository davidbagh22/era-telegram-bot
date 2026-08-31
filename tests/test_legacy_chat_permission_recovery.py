from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services.chat_permissions_service import restore_general_chat_member


def test_restore_general_chat_member_unrestricts_legacy_restricted_member() -> None:
    async def scenario() -> None:
        bot = SimpleNamespace(
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(status=SimpleNamespace(value="restricted"))
            ),
            restrict_chat_member=AsyncMock(),
        )
        settings = SimpleNamespace(general_chat_id=-100123)

        repaired = await restore_general_chat_member(bot, settings, 777)

        assert repaired is True
        bot.get_chat_member.assert_awaited_once_with(chat_id=-100123, user_id=777)
        bot.restrict_chat_member.assert_awaited_once()
        kwargs = bot.restrict_chat_member.await_args.kwargs
        assert kwargs["chat_id"] == -100123
        assert kwargs["user_id"] == 777
        assert kwargs["permissions"].can_send_messages is True

    asyncio.run(scenario())


def test_restore_general_chat_member_does_not_touch_banned_or_normal_members() -> None:
    async def scenario() -> None:
        for status in ("member", "administrator", "creator", "kicked", "left"):
            bot = SimpleNamespace(
                get_chat_member=AsyncMock(
                    return_value=SimpleNamespace(status=SimpleNamespace(value=status))
                ),
                restrict_chat_member=AsyncMock(),
            )
            settings = SimpleNamespace(general_chat_id=-100123)

            repaired = await restore_general_chat_member(bot, settings, 777)

            assert repaired is False
            bot.restrict_chat_member.assert_not_awaited()

    asyncio.run(scenario())


def test_recovery_is_wired_before_start_router() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app/bot.py").read_text(
        encoding="utf-8"
    )
    assert "LegacyChatPermissionRecoveryMiddleware(settings)" in source
    assert "chat_unlock.router" in source
    assert source.index("chat_unlock.router") < source.index("start.router")
