"""Wave-1 reply keyboard: short labels, leaders/media only with rights."""

from app.keyboards.bot_shell import ADMIN_HUB_BUTTON, admin_hub_keyboard, main_reply_keyboard
from app.services.anniversary_registration_service import MENU_BUTTON, MENU_TICKET_BUTTON


def _texts(markup) -> set[str]:
    return {button.text for row in markup.keyboard for button in row}


def test_participant_reply_keyboard_is_short_and_has_no_empty_leader_shell():
    markup = main_reply_keyboard("https://era.example/app/")
    texts = _texts(markup)
    assert "🔥 Открыть ЭРА" in texts
    assert "📅 Афиша" in texts
    assert "🌱 Мой путь" in texts
    assert "⭐ Возможности" in texts
    assert "💬 Связь" in texts
    assert "🧭 Лидеры" not in texts
    assert "🎬 Медиа" not in texts
    assert "🧭 Навигация" not in texts
    assert "🎲 Досуг" not in texts
    assert ADMIN_HUB_BUTTON not in texts
    assert "📊 Статистика" not in texts
    assert "📥 Заявки" not in texts


def test_leaders_and_media_share_one_row_when_both_present():
    markup = main_reply_keyboard(
        "https://era.example/app/", leaders=True, media_chair=True,
    )
    role_rows = [
        row for row in markup.keyboard
        if {button.text for button in row} == {"🧭 Лидеры", "🎬 Медиа"}
    ]
    assert len(role_rows) == 1


def test_leaders_and_media_appear_only_with_rights():
    leaders = _texts(main_reply_keyboard("https://era.example/app/", leaders=True))
    media = _texts(main_reply_keyboard("https://era.example/app/", media_chair=True))
    admin = _texts(main_reply_keyboard("https://era.example/app/", admin=True))
    assert "🧭 Лидеры" in leaders
    assert "🎬 Медиа" in media
    assert "🎬 Руководитель медиа" not in media
    assert "🧭 Лидеры" not in admin
    assert ADMIN_HUB_BUTTON in admin
    assert "📊 Статистика" not in admin
    assert "📥 Заявки" not in admin


def test_admin_hub_exposes_stats_and_applications():
    buttons = [
        button
        for row in admin_hub_keyboard("https://era.example/app/").inline_keyboard
        for button in row
    ]
    callbacks = {button.callback_data for button in buttons}
    assert {"admin:management:open", "admin:applications", "menu:main"} <= callbacks
    assert any(button.web_app and button.text == "⚙️ Управление ЭРА" for button in buttons)


def test_anniversary_button_switches_to_ticket_when_registered():
    open_texts = _texts(main_reply_keyboard("https://era.example/app/", anniversary=True))
    ticket_texts = _texts(
        main_reply_keyboard(
            "https://era.example/app/",
            anniversary=True,
            anniversary_registered=True,
        )
    )
    assert MENU_BUTTON in open_texts
    assert MENU_TICKET_BUTTON not in open_texts
    assert MENU_TICKET_BUTTON in ticket_texts
    assert MENU_BUTTON not in ticket_texts
