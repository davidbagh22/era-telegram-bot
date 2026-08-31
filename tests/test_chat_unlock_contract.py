from pathlib import Path


def test_unlock_command_is_private_and_reports_success() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/handlers/chat_unlock.py").read_text(encoding="utf-8")
    assert 'Command("unlock_chat")' in source
    assert 'F.chat.type == "private"' in source
    assert "restore_general_chat_member" in source
    assert "Старое ограничение" in source
