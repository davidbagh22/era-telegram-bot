from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services.chat_permissions_service import enforce_general_chat_writable


def test_scheduled_general_chat_permission_hook_is_a_safe_noop() -> None:
    async def scenario() -> None:
        bot = SimpleNamespace(
            set_chat_permissions=AsyncMock(),
            get_chat_member=AsyncMock(),
            restrict_chat_member=AsyncMock(),
        )
        result = await enforce_general_chat_writable(
            bot,
            SimpleNamespace(general_chat_id=-100123),
            AsyncMock(),
        )

        assert result == (0, 0)
        bot.set_chat_permissions.assert_not_awaited()
        bot.get_chat_member.assert_not_awaited()
        bot.restrict_chat_member.assert_not_awaited()

    asyncio.run(scenario())


def test_automatic_recovery_is_removed_but_unlock_command_remains_routable() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app/bot.py").read_text(
        encoding="utf-8"
    )
    assert "LegacyChatPermissionRecoveryMiddleware" not in source
    assert "chat_unlock.router" in source
    assert source.index("chat_unlock.router") < source.index("start.router")
