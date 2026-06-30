import hashlib
import hmac
import json
import unittest
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from app.services.telegram_auth_service import validate_init_data


BOT_TOKEN = "test-token-for-mini-app-signatures"


def signed_init_data(auth_date: datetime) -> str:
    values = {
        "auth_date": str(int(auth_date.timestamp())),
        "query_id": "AAEAAAE",
        "user": json.dumps(
            {
                "id": 1593868942,
                "first_name": "Давид",
                "last_name": "Багдасарян",
                "username": "era_admin",
                "language_code": "ru",
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode(values)


class TelegramMiniAppAuthTests(unittest.TestCase):
    def test_valid_init_data(self) -> None:
        now = datetime.now(UTC)
        identity = validate_init_data(signed_init_data(now), BOT_TOKEN, now=now)
        self.assertEqual(identity.telegram_id, 1593868942)
        self.assertEqual(identity.first_name, "Давид")

    def test_modified_init_data_is_rejected(self) -> None:
        now = datetime.now(UTC)
        payload = signed_init_data(now).replace("1593868942", "1593868943")
        with self.assertRaisesRegex(ValueError, "signature"):
            validate_init_data(payload, BOT_TOKEN, now=now)

    def test_expired_init_data_is_rejected(self) -> None:
        now = datetime.now(UTC)
        payload = signed_init_data(now - timedelta(days=2))
        with self.assertRaisesRegex(ValueError, "expired"):
            validate_init_data(payload, BOT_TOKEN, now=now, max_age_seconds=3600)


if __name__ == "__main__":
    unittest.main()
