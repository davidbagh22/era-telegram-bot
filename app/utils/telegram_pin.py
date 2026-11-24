"""Shared Telegram pin helpers — treat already-pinned as durable success."""
from __future__ import annotations


def telegram_already_pinned(exc: BaseException) -> bool:
    code = str(exc).upper().replace(" ", "_").replace("-", "_")
    return "MESSAGE_IS_ALREADY_PINNED" in code or "MESSAGE_ALREADY_PINNED" in code
