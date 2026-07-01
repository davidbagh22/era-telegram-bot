import unittest

from app.utils.validators import (
    clean_text,
    normalize_email,
    normalize_phone,
    parse_age,
    parse_date,
    parse_time,
)


class ValidatorTests(unittest.TestCase):
    def test_age_bounds(self) -> None:
        self.assertEqual(parse_age("18"), 18)
        self.assertIsNone(parse_age("13"))
        self.assertIsNone(parse_age("abc"))

    def test_phone_normalization(self) -> None:
        self.assertEqual(normalize_phone("+374 99 123-456"), "+37499123456")
        self.assertIsNone(normalize_phone("123"))

    def test_email_normalization(self) -> None:
        self.assertEqual(normalize_email(" Test@Example.com "), "test@example.com")
        self.assertIsNone(normalize_email("not-an-email"))

    def test_date_and_time(self) -> None:
        self.assertEqual(parse_date("30.06.2026").isoformat(), "2026-06-30")
        self.assertEqual(parse_time("19:30").isoformat(), "19:30:00")
        self.assertIsNone(parse_date("2026-06-30"))
        self.assertIsNone(parse_time("25:00"))

    def test_clean_text(self) -> None:
        self.assertEqual(clean_text("  ЭРА\n  движется  "), "ЭРА движется")
        self.assertIsNone(clean_text("   "))


if __name__ == "__main__":
    unittest.main()
