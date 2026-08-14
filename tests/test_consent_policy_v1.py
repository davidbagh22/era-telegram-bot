from __future__ import annotations

import inspect
import unittest

from app.handlers.registration import finish_registration, registration_social
from app.keyboards.registration import consent_keyboard
from app.services.consent_policy import (
    CONSENT_FULL_TEXT,
    CONSENT_POLICY_VERSION,
    CONSENT_SUMMARY,
    TELEGRAM_SAFE_TEXT_LIMIT,
    consent_full_chunks,
)
from app.services.consent_service import CURRENT_POLICY_VERSION


class ConsentPolicyV1Tests(unittest.TestCase):
    def test_policy_is_real_version_not_placeholder(self) -> None:
        self.assertEqual(CURRENT_POLICY_VERSION, CONSENT_POLICY_VERSION)
        self.assertEqual(CONSENT_POLICY_VERSION, "pd-v1-2026-08-15")
        self.assertNotIn("unset", CONSENT_POLICY_VERSION)

    def test_same_form_covers_every_age(self) -> None:
        combined = f"{CONSENT_SUMMARY}\n{CONSENT_FULL_TEXT}"
        self.assertIn("До 16 лет", CONSENT_SUMMARY)
        self.assertIn("законный представитель", combined)
        self.assertIn("Для всех используется одна и та же форма", CONSENT_FULL_TEXT)

        # The live consent transition itself must not branch on age. Age is
        # collected earlier in registration, but approval of this form is
        # the same callback for every participant.
        source = inspect.getsource(registration_social) + inspect.getsource(finish_registration)
        self.assertNotIn("is_minor", source)
        self.assertNotIn("birth_date", source)
        self.assertNotIn("age <", source)

    def test_summary_is_scannable_and_names_the_core_terms(self) -> None:
        for marker in [
            "Что мы используем",
            "Зачем",
            "Кто имеет доступ",
            "Ваши права",
            "До 16 лет",
            "фото, видео, документы",
            "Согласен и продолжить",
        ]:
            self.assertIn(marker, CONSENT_SUMMARY)

    def test_full_policy_is_safe_for_telegram_delivery(self) -> None:
        chunks = consent_full_chunks()
        self.assertGreaterEqual(len(chunks), 1)
        self.assertEqual("\n\n".join(chunks), CONSENT_FULL_TEXT)
        self.assertTrue(all(len(chunk) <= TELEGRAM_SAFE_TEXT_LIMIT for chunk in chunks))

    def test_keyboard_has_explicit_accept_full_terms_and_decline(self) -> None:
        keyboard = consent_keyboard()
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        labels = {button.text for button in buttons}
        callbacks = {button.callback_data for button in buttons}
        self.assertIn("✅ Согласен и продолжить", labels)
        self.assertIn("📄 Полные условия", labels)
        self.assertIn("reg:consent:yes", callbacks)
        self.assertIn("reg:consent:full", callbacks)
        self.assertIn("reg:consent:no", callbacks)

    def test_form_records_version_and_rejects_stale_display(self) -> None:
        social_source = inspect.getsource(registration_social)
        finish_source = inspect.getsource(finish_registration)
        self.assertIn("consent_policy_version=CURRENT_POLICY_VERSION", social_source)
        stale_check = finish_source.index(
            'data.get("consent_policy_version") != CURRENT_POLICY_VERSION'
        )
        create_user = finish_source.index("create_user_from_registration")
        self.assertLess(stale_check, create_user)


if __name__ == "__main__":
    unittest.main()
