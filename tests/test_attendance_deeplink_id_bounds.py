"""Bounds for untrusted QR attendance deep-link event IDs.

Pure parser checks; no Telegram, database, attendance, or points mutations.
"""
import unittest

from app.services.event_attendance_service import parse_confirmation_payload


class AttendanceDeepLinkIdBoundsTests(unittest.TestCase):
    def test_valid_postgres_ids_keep_existing_contract(self):
        for event_id in (1, 42, 2_147_483_647):
            with self.subTest(event_id=event_id):
                self.assertEqual(
                    parse_confirmation_payload(f"attend2_{event_id}_ABCDEFGH"),
                    (event_id, "ABCDEFGH"),
                )

    def test_invalid_or_oversized_ids_are_rejected(self):
        for raw in (
            "attend2_2147483648_ABCDEFGH",
            "attend2_9999999999_ABCDEFGH",
            "attend2_0000000001_ABCDEFGH",
            "attend2_0_ABCDEFGH",
            "attend2_-1_ABCDEFGH",
            "attend2_４２_ABCDEFGH",
            "attend2_42_ABCDEFG",
            "attend2_42_ABCDEFGHI",
            "attend2_42_abcdefgh",
            "attend2_42_ABCDEFGH_extra",
            "attend2_" + "9" * 5000 + "_ABCDEFGH",
        ):
            with self.subTest(raw=raw[:50]):
                self.assertIsNone(parse_confirmation_payload(raw))


if __name__ == "__main__":
    unittest.main()
