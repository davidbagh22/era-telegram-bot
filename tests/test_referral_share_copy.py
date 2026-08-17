from app.services.referral_service import _share_text


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
    assert "по 200 баллов" in text
    assert "по 500 баллов каждому" in text
    assert "через людей, опыт и реальные действия" in text
