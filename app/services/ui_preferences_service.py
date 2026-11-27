from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.ui_preferences import UserUiPreference

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class InvalidAccentColor(ValueError):
    pass


def normalize_accent_color(value: str | None) -> str | None:
    """Return a canonical lowercase ``#rrggbb`` (or None to reset to default)."""
    if value is None:
        return None
    candidate = value.strip()
    if not _HEX_COLOR.fullmatch(candidate):
        raise InvalidAccentColor(candidate[:16])
    return candidate.lower()


async def get_ui_preferences(session: AsyncSession, user_id: int) -> UserUiPreference | None:
    return await session.get(UserUiPreference, user_id)


async def set_accent_color(
    session: AsyncSession, user_id: int, accent_color: str | None
) -> UserUiPreference:
    normalized = normalize_accent_color(accent_color)
    row = await session.get(UserUiPreference, user_id)
    if row is None:
        row = UserUiPreference(user_id=user_id, accent_color=normalized)
        session.add(row)
    else:
        row.accent_color = normalized
    await session.flush()
    await session.refresh(row)
    return row
