"""Wave-1 reply keyboard: short labels, leaders/media only with rights."""

from app.keyboards.bot_shell import main_reply_keyboard


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


def test_leaders_and_media_appear_only_with_rights():
    leaders = _texts(main_reply_keyboard("https://era.example/app/", leaders=True))
    media = _texts(main_reply_keyboard("https://era.example/app/", media_chair=True))
    admin = _texts(main_reply_keyboard("https://era.example/app/", admin=True))
    assert "🧭 Лидеры" in leaders
    assert "🎬 Медиа" in media
    assert "🎬 Руководитель медиа" not in media
    assert "🧭 Лидеры" not in admin
    assert "📊 Статистика" in admin
    assert "📥 Заявки" in admin
