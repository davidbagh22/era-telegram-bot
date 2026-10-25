import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.handlers.chat_unlock import unlock_general_chat


def test_unlock_command_is_private_and_directs_user_to_moderators() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/handlers/chat_unlock.py").read_text(encoding="utf-8")
    assert 'Command("unlock_chat")' in source
    assert 'F.chat.type == "private"' in source

    async def scenario() -> None:
        message = SimpleNamespace(answer=AsyncMock())
        await unlock_general_chat(message)
        message.answer.assert_awaited_once()
        assert "модераторы" in message.answer.await_args.args[0]

    asyncio.run(scenario())
