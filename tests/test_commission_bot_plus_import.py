def test_commission_bot_plus_imports():
    from app.commission_bot_plus import CommissionBotPlus, ROLE_LABELS

    assert ROLE_LABELS["admin"] == "Администратор"
    assert ROLE_LABELS["editor"] == "Модератор"
    assert CommissionBotPlus is not None
