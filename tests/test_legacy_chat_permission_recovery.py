from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services.chat_permissions_service import (
    enforce_general_chat_writable,
    restore_general_chat_member,
)


def test_restore_never_overrides_a_human_moderator_restriction() -> None:
    async def scenario() -> None:
        for status in ("restricted", "member", "administrator", "creator", "kicked", "left"):
            bot = SimpleNamespace(
                get_chat_member=AsyncMock(
                    return_value=SimpleNamespace(status=SimpleNamespace(value=status))
                ),
                restrict_chat_member=AsyncMock(),
                set_chat_permissions=AsyncMock(),
                ban_chat_member=AsyncMock(),
            )
            settings = SimpleNamespace(general_chat_id=-100123)

            repaired = await restore_general_chat_member(bot, settings, 777)

            assert repaired is False
            bot.get_chat_member.assert_not_awaited()
            bot.restrict_chat_member.assert_not_awaited()
            bot.set_chat_permissions.assert_not_awaited()
            bot.ban_chat_member.assert_not_awaited()

    asyncio.run(scenario())


def test_scheduled_chat_permission_enforcement_is_non_mutating() -> None:
    async def scenario() -> None:
        bot = SimpleNamespace(
            get_chat_member=AsyncMock(),
            restrict_chat_member=AsyncMock(),
            set_chat_permissions=AsyncMock(),
            ban_chat_member=AsyncMock(),
        )
        settings = SimpleNamespace(general_chat_id=-100123)

        assert await enforce_general_chat_writable(bot, settings, object()) == (0, 0)
        bot.get_chat_member.assert_not_awaited()
        bot.restrict_chat_member.assert_not_awaited()
        bot.set_chat_permissions.assert_not_awaited()
        bot.ban_chat_member.assert_not_awaited()

    asyncio.run(scenario())


def test_recovery_is_wired_before_start_router() -> None:
    source = (Path(__file__).resolve().parents[1] / "app/bot.py").read_text(
        encoding="utf-8"
    )
    assert "LegacyChatPermissionRecoveryMiddleware(settings)" in source
    assert "chat_unlock.router" in source
    assert source.index("chat_unlock.router") < source.index("start.router")
