from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class InitDataError(ValueError):
    """Telegram WebApp initData failed signature or freshness checks."""


class SessionTokenError(ValueError):
    """Mini App session token is missing, malformed, tampered or expired."""


@dataclass(frozen=True)
class TelegramInitData:
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    auth_date: int


def verify_init_data(
    init_data: str, *, bot_token: str, max_age_seconds: int
) -> TelegramInitData:
    """Verify Telegram WebApp initData per Telegram's HMAC scheme.

    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data:
        raise InitDataError("empty_init_data")

    data = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise InitDataError("missing_hash")

    check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(
        secret_key, check_string.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(computed_hash, received_hash):
        raise InitDataError("invalid_signature")

    try:
        auth_date = int(data["auth_date"])
    except (KeyError, ValueError) as exc:
        raise InitDataError("missing_auth_date") from exc
    if max_age_seconds > 0 and time.time() - auth_date > max_age_seconds:
        raise InitDataError("expired")

    try:
        user_payload = json.loads(data["user"])
    except (KeyError, ValueError) as exc:
        raise InitDataError("missing_user") from exc

    telegram_id = user_payload.get("id")
    if not isinstance(telegram_id, int):
        raise InitDataError("missing_user_id")

    return TelegramInitData(
        telegram_id=telegram_id,
        username=user_payload.get("username"),
        first_name=user_payload.get("first_name"),
        last_name=user_payload.get("last_name"),
        auth_date=auth_date,
    )


@dataclass(frozen=True)
class SessionTokenPayload:
    telegram_id: int
    expires_at: int


def create_session_token(
    *, telegram_id: int, secret: str, ttl_seconds: int
) -> tuple[str, int]:
    if not secret:
        raise SessionTokenError("missing_secret")
    expires_at = int(time.time()) + ttl_seconds
    payload = f"{telegram_id}:{expires_at}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    encoded_payload = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    return f"{encoded_payload}.{signature}", expires_at


def decode_session_token(token: str, secret: str) -> SessionTokenPayload:
    if not secret:
        raise SessionTokenError("missing_secret")
    try:
        encoded_payload, signature = token.split(".", 1)
    except ValueError as exc:
        raise SessionTokenError("malformed_token") from exc

    padding = "=" * (-len(encoded_payload) % 4)
    try:
        payload = base64.urlsafe_b64decode(encoded_payload + padding).decode()
    except Exception as exc:
        raise SessionTokenError("malformed_token") from exc

    expected_signature = hmac.new(
        secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        raise SessionTokenError("invalid_signature")

    try:
        telegram_id_str, expires_at_str = payload.split(":", 1)
        telegram_id = int(telegram_id_str)
        expires_at = int(expires_at_str)
    except ValueError as exc:
        raise SessionTokenError("malformed_token") from exc

    if time.time() > expires_at:
        raise SessionTokenError("expired")

    return SessionTokenPayload(telegram_id=telegram_id, expires_at=expires_at)
