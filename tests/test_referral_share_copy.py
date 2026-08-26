from app.services.referral_service import (
    FIRST_ACTIVITY_REFERRAL_POINTS,
    REFERRAL_MONTHLY_CAP,
    REFERRAL_PER_INVITEE_CAP,
    REGISTRATION_REFERRAL_POINTS,
    _share_text,
)


def test_referral_share_text_contains_context_bot_code_and_rewards() -> None:
    text = _share_text(
        "181239",
        "https://t.me/ERA_1bot?start=ref_181239",
        "https://t.me/+Q6MzTrnR21dmZjgy",
    )

    assert text.startswith("Присоединяйся к ЭРА 🔥")
    assert "через реальные проекты" in text
    assert "https://t.me/ERA_1bot?start=ref_181239" in text
    assert "При регистрации введи мой код: 181239" in text
    assert f"+{REGISTRATION_REFERRAL_POINTS}" in text
    assert f"+{FIRST_ACTIVITY_REFERRAL_POINTS}" in text
    assert REFERRAL_PER_INVITEE_CAP == 100
    assert REFERRAL_MONTHLY_CAP == 0
    assert "не за ссылку и не за вступление в чат" in text
    assert "после первого подтверждённого участия" in text
