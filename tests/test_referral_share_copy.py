from app.services.referral_service import (
    FIRST_EVENT_REFERRAL_POINTS,
    REGISTRATION_REFERRAL_POINTS,
    _share_text,
)


def test_referral_share_text_matches_economy_v2() -> None:
    text = _share_text(
        "181239",
        "https://t.me/ERA_1bot?start=ref_181239",
        "https://t.me/+Q6MzTrnR21dmZjgy",
    )

    assert text.startswith("Присоединяйся к ЭРА 🔥")
    assert "через реальные проекты, события и возможности" in text
    assert "https://t.me/ERA_1bot?start=ref_181239" in text
    assert "При регистрации введи мой код: 181239" in text
    assert "не за ссылку и не за вступление в чат" in text
    assert f"+{REGISTRATION_REFERRAL_POINTS}" in text
    assert f"+{FIRST_EVENT_REFERRAL_POINTS}" in text
    assert "после одобрения регистрации" in text
    assert "после первого подтверждённого участия" in text
