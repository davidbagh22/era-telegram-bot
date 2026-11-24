from __future__ import annotations

import hashlib
import hmac
import json
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from app.api.security import (
    InitDataError,
    SessionTokenError,
    create_session_token,
    decode_session_token,
    verify_init_data,
)

BOT_TOKEN = "1234567890:test-token"


def _signed_init_data(
    *,
    telegram_id: int = 555,
    auth_date: int | None = None,
    username: str = "dev_user",
    first_name: str = "Dev",
) -> str:
    fields = {
        "query_id": "AAH_test",
        "user": json.dumps(
            {"id": telegram_id, "first_name": first_name, "username": username}
        ),
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
    }
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(
        secret_key, check_string.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode(fields)


class VerifyInitDataTests(unittest.TestCase):
    def test_valid_init_data_is_accepted(self) -> None:
        result = verify_init_data(
            _signed_init_data(), bot_token=BOT_TOKEN, max_age_seconds=86400
        )
        self.assertEqual(result.telegram_id, 555)
        self.assertEqual(result.username, "dev_user")

    def test_empty_init_data_is_rejected(self) -> None:
        with self.assertRaises(InitDataError):
            verify_init_data("", bot_token=BOT_TOKEN, max_age_seconds=86400)

    def test_missing_hash_is_rejected(self) -> None:
        with self.assertRaises(InitDataError):
            verify_init_data(
                "auth_date=1&user=%7B%7D", bot_token=BOT_TOKEN, max_age_seconds=86400
            )

    def test_tampered_payload_is_rejected(self) -> None:
        tampered = _signed_init_data(telegram_id=555).replace("555", "999")
        with self.assertRaises(InitDataError):
            verify_init_data(tampered, bot_token=BOT_TOKEN, max_age_seconds=86400)

    def test_wrong_bot_token_is_rejected(self) -> None:
        data = _signed_init_data()
        with self.assertRaises(InitDataError):
            verify_init_data(data, bot_token="other:token", max_age_seconds=86400)

    def test_expired_init_data_is_rejected(self) -> None:
        stale = _signed_init_data(auth_date=int(time.time()) - 999_999)
        with self.assertRaises(InitDataError):
            verify_init_data(stale, bot_token=BOT_TOKEN, max_age_seconds=86400)

    def test_excessive_init_data_fields_are_rejected_before_signature_check(self) -> None:
        # A normal Telegram payload has only a handful of query parameters.
        oversized = _signed_init_data() + "".join(
            f"&extra_{index}=x" for index in range(61)
        )
        with self.assertRaisesRegex(InitDataError, "invalid_fields"):
            verify_init_data(
                oversized, bot_token=BOT_TOKEN, max_age_seconds=86400
            )

    def test_excessive_init_data_length_is_rejected_before_parsing(self) -> None:
        oversized = _signed_init_data() + "&padding=" + ("x" * 16_384)
        with self.assertRaisesRegex(InitDataError, "init_data_too_large"):
            verify_init_data(
                oversized, bot_token=BOT_TOKEN, max_age_seconds=86400
            )

    def test_duplicate_signed_fields_are_rejected(self) -> None:
        # A duplicate query parameter is not a second authenticated identity.
        valid = _signed_init_data()
        with self.assertRaisesRegex(InitDataError, "duplicate_field"):
            verify_init_data(
                valid + "&auth_date=1", bot_token=BOT_TOKEN, max_age_seconds=86400
            )

    def test_future_auth_date_is_rejected_but_small_clock_skew_is_allowed(self) -> None:
        now = int(time.time())
        with self.assertRaisesRegex(InitDataError, "future_auth_date"):
            verify_init_data(
                _signed_init_data(auth_date=now + 3600),
                bot_token=BOT_TOKEN,
                max_age_seconds=86400,
            )
        result = verify_init_data(
            _signed_init_data(auth_date=now + 30),
            bot_token=BOT_TOKEN,
            max_age_seconds=86400,
        )
        self.assertEqual(result.telegram_id, 555)

    def test_invalid_signed_user_ids_are_rejected(self) -> None:
        for invalid_id in (True, 0, -1):
            with self.subTest(telegram_id=invalid_id), self.assertRaisesRegex(
                InitDataError, "missing_user_id"
            ):
                verify_init_data(
                    _signed_init_data(telegram_id=invalid_id),
                    bot_token=BOT_TOKEN,
                    max_age_seconds=86400,
                )

    def test_signed_non_object_user_is_rejected(self) -> None:
        fields = {"auth_date": str(int(time.time())), "user": "null"}
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        fields["hash"] = hmac.new(
            secret_key, check_string.encode(), hashlib.sha256
        ).hexdigest()
        with self.assertRaisesRegex(InitDataError, "missing_user"):
            verify_init_data(
                urlencode(fields), bot_token=BOT_TOKEN, max_age_seconds=86400
            )

    def test_max_age_zero_disables_freshness_check(self) -> None:
        stale = _signed_init_data(auth_date=int(time.time()) - 999_999)
        result = verify_init_data(stale, bot_token=BOT_TOKEN, max_age_seconds=0)
        self.assertEqual(result.telegram_id, 555)


class SessionTokenTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        token, expires_at = create_session_token(
            telegram_id=42, secret="s3cr3t", ttl_seconds=3600
        )
        payload = decode_session_token(token, "s3cr3t")
        self.assertEqual(payload.telegram_id, 42)
        self.assertEqual(payload.expires_at, expires_at)

    def test_wrong_secret_is_rejected(self) -> None:
        token, _ = create_session_token(telegram_id=42, secret="s3cr3t", ttl_seconds=3600)
        with self.assertRaises(SessionTokenError):
            decode_session_token(token, "other-secret")

    def test_tampered_token_is_rejected(self) -> None:
        token, _ = create_session_token(telegram_id=42, secret="s3cr3t", ttl_seconds=3600)
        encoded_payload, signature = token.split(".", 1)
        tampered = f"{encoded_payload}x.{signature}"
        with self.assertRaises(SessionTokenError):
            decode_session_token(tampered, "s3cr3t")

    def test_expired_token_is_rejected(self) -> None:
        token, _ = create_session_token(telegram_id=42, secret="s3cr3t", ttl_seconds=-10)
        with self.assertRaises(SessionTokenError):
            decode_session_token(token, "s3cr3t")

    def test_oversized_bearer_token_is_rejected_before_decoding(self) -> None:
        # The API receives untrusted Authorization headers; oversized values
        # must not reach base64 decoding or HMAC verification.
        with patch(
            "app.api.security.base64.urlsafe_b64decode",
            side_effect=AssertionError("must not decode oversized token"),
        ):
            with self.assertRaisesRegex(SessionTokenError, "malformed_token"):
                decode_session_token("A" * 100_000 + "." + "0" * 64, "s3cr3t")

    def test_signed_nonpositive_telegram_id_is_rejected(self) -> None:
        for invalid_id in (0, -1):
            with self.subTest(telegram_id=invalid_id):
                token, _ = create_session_token(
                    telegram_id=invalid_id, secret="s3cr3t", ttl_seconds=3600
                )
                with self.assertRaisesRegex(SessionTokenError, "malformed_token"):
                    decode_session_token(token, "s3cr3t")

    def test_token_expires_at_exact_boundary(self) -> None:
        with patch("app.api.security.time.time", return_value=1000):
            token, expires_at = create_session_token(
                telegram_id=42, secret="s3cr3t", ttl_seconds=60
            )
        self.assertEqual(expires_at, 1060)
        with patch("app.api.security.time.time", return_value=1060):
            with self.assertRaisesRegex(SessionTokenError, "expired"):
                decode_session_token(token, "s3cr3t")

    def test_missing_secret_raises(self) -> None:
        with self.assertRaises(SessionTokenError):
            create_session_token(telegram_id=42, secret="", ttl_seconds=3600)
        with self.assertRaises(SessionTokenError):
            decode_session_token("a.b", "")

    def test_malformed_token_is_rejected(self) -> None:
        with self.assertRaises(SessionTokenError):
            decode_session_token("not-a-token", "s3cr3t")


if __name__ == "__main__":
    unittest.main()
