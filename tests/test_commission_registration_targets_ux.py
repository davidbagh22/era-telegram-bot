from pathlib import Path

from app.commission_bot_hardened import CommissionBotHardened
from app.commission_bot_simple_ux import _country_code_from_text


def test_typed_country_registration_normalizes_common_inputs():
    assert _country_code_from_text("Армения") == "AM"
    assert _country_code_from_text("Россия") == "RU"
    assert _country_code_from_text("РФ") == "RU"
    assert _country_code_from_text("KZ") == "KZ"
    assert _country_code_from_text("не страна") is None


def test_target_connector_keyboard_is_valid_and_requests_existing_chats():
    app = object.__new__(CommissionBotHardened)
    keyboard = app._target_connect_keyboard()
    buttons = [button for row in keyboard.keyboard for button in row if button.request_chat]
    assert len(buttons) == 2
    assert buttons[0].request_chat.chat_is_channel is False
    assert buttons[1].request_chat.chat_is_channel is True
    assert all(button.request_chat.bot_is_member is True for button in buttons)


def test_simple_quick_navigation_uses_dispatcher_labels():
    source = Path("app/commission_bot_simple_ux.py").read_text(encoding="utf-8")
    assert 'KeyboardButton(text="📅 Мероприятия")' in source
    assert 'KeyboardButton(text="🎟 Мои регистрации")' in source
    assert 'KeyboardButton(text="📅 События")' not in source
    assert 'KeyboardButton(text="🎟 Мои заявки")' not in source


def test_commission_registration_does_not_touch_era_profile_reset():
    webapp = Path("app/webapp.py").read_text(encoding="utf-8")
    assert "ERA_REREGISTRATION_RESET_TELEGRAM_ID" not in webapp
    assert "COMMISSION_RESET_TELEGRAM_ID" in webapp


def test_commission_profile_has_region_migration():
    source = Path("app/commission_bot_engagement.py").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS region_name TEXT" in source
