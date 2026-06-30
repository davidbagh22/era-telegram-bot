from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qsl


@dataclass(frozen=True, slots=True)
class TelegramIdentity:
    telegram_id: int
    username: str | None
    first_name: str
    last_name: str | None
    language_code: str | None = None


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = 86400,
    now: datetime | None = None,
) -> TelegramIdentity:
    try:
        values = dict(parse_qsl(init_data, strict_parsing=True))
        received_hash = values.pop("hash")
        auth_date = int(values["auth_date"])
        user_data = json.loads(values["user"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid Telegram init data") from exc

    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
    ).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("Telegram init data signature mismatch")

    current_time = now or datetime.now(UTC)
    age = current_time.timestamp() - auth_date
    if age < -30 or age > max_age_seconds:
        raise ValueError("Telegram init data is expired")

    try:
        return TelegramIdentity(
            telegram_id=int(user_data["id"]),
            username=user_data.get("username"),
            first_name=str(user_data.get("first_name") or "Участник"),
            last_name=user_data.get("last_name"),
            language_code=user_data.get("language_code"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Telegram user data is invalid") from exc
