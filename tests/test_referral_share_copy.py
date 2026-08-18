from app.services.referral_service import (
    ACTIVE_REFERRAL_POINTS,
    FIRST_EVENT_REFERRAL_POINTS,
    REFERRAL_MONTHLY_CAP,
    REFERRAL_PER_INVITEE_CAP,
    REGISTRATION_REFERRAL_POINTS,
    _share_text,
)


def test_referral_share_text_contains_context_bot_chat_code_and_rewards() -> None:
    text = _share_text(
        "181239",
        "https://t.me/ERA_1bot?start=ref_181239",
        "https://t.me/+Q6MzTrnR21dmZjgy",
    )

    assert text.startswith("Присоединяйся к ЭРА 🔥")
    assert "реальных проектах" in text
    assert "Мой вектор" in text
    assert "выбрать следующий шаг" in text
    assert "@ERA_1bot" in text
    assert "https://t.me/ERA_1bot?start=ref_181239" in text
    assert "https://t.me/+Q6MzTrnR21dmZjgy" in text
    assert "При регистрации введи мой код: 181239" in text
    assert f"по {REGISTRATION_REFERRAL_POINTS}" in text
    assert f"по {FIRST_EVENT_REFERRAL_POINTS}" in text
    assert f"по {ACTIVE_REFERRAL_POINTS}" in text
    assert f"до {REFERRAL_PER_INVITEE_CAP} баллов" in text
    assert f"лимит {REFERRAL_MONTHLY_CAP} реферальных баллов в месяц" in text
    assert "через людей, опыт и реальные действия" in text
