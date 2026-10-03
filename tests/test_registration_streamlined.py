from __future__ import annotations

from pathlib import Path

from app.database.models import User
from app.keyboards.registration import consent_keyboard, time_keyboard
from app.states.registration import RegistrationStates


def test_streamlined_registration_has_explicit_identity_location_states() -> None:
    assert hasattr(RegistrationStates, "full_name")
    assert hasattr(RegistrationStates, "age")
    assert hasattr(RegistrationStates, "country")
    assert hasattr(RegistrationStates, "region")
    assert hasattr(RegistrationStates, "review")


def test_user_profile_has_country_and_region_columns() -> None:
    assert "country" in User.__table__.columns
    assert "region" in User.__table__.columns


def test_registration_no_longer_requires_photo_or_social_link() -> None:
    source = Path("app/handlers/registration.py").read_text(encoding="utf-8")
    assert "Для регистрации нужны фото профиля и ссылка на соцсеть" not in source
    assert 'if data.get("social_url"):' in source


def test_registration_uses_three_clear_availability_choices() -> None:
    markup = time_keyboard()
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert labels == [
        "1–2 часа в неделю",
        "3–5 часов в неделю",
        "Готов активно включаться",
    ]


def test_consent_screen_contains_no_dead_referral_action() -> None:
    markup = consent_keyboard()
    callbacks = {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }
    assert "reg:ref:start" not in callbacks
