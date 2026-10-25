from pathlib import Path


def test_simple_ux_opens_targets_with_callback_contract():
    source = Path("app/commission_bot_simple_ux.py").read_text(encoding="utf-8")
    assert 'if action == "targets":' in source
    assert "return await self._show_targets(c)" in source
    assert "self._show_targets(c.message.chat.id, user)" not in source


def test_target_membership_and_delivery_guards_are_present():
    core = Path("app/commission_bot.py").read_text(encoding="utf-8")
    hardened = Path("app/commission_bot_hardened.py").read_text(encoding="utf-8")
    assert "@r.my_chat_member()" in core
    assert "INSERT INTO targets" in core
    assert "bot_can_post=TRUE" in hardened
    assert "status='approved'" in hardened
