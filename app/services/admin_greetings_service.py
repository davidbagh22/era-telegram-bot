"""Chat-greeting management — shared by the bot's "👋 Автоматические
приветствия" flow (app/handlers/admin/panel.py) and the Mini App's admin
tools. Covers exactly the bot's existing scope: toggling a greeting on/off
and editing its text (with {name} placeholder support). `title` stays
fixed/seeded (see app/services/seed_service.py's GREETING_DEFAULTS) — the
bot never let admins rename a greeting, so neither does this.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ChatGreeting

MAX_TEXT_LENGTH = 3000


class GreetingError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(slots=True)
class GreetingOut:
    id: int
    chat_key: str
    title: str
    text: str
    is_enabled: bool
    is_bound: bool


def _to_out(item: ChatGreeting) -> GreetingOut:
    return GreetingOut(
        id=item.id,
        chat_key=item.chat_key,
        title=item.title,
        text=item.text,
        is_enabled=item.is_enabled,
        is_bound=item.chat_id is not None,
    )


async def list_greetings(session: AsyncSession) -> list[GreetingOut]:
    items = (await session.scalars(select(ChatGreeting).order_by(ChatGreeting.id))).all()
    return [_to_out(item) for item in items]


async def update_greeting_text(
    session: AsyncSession, greeting_id: int, text: str, updated_by: int | None
) -> ChatGreeting:
    text = text.strip()[:MAX_TEXT_LENGTH]
    if not text:
        raise GreetingError("text_required")
    item = await session.get(ChatGreeting, greeting_id)
    if item is None:
        raise GreetingError("greeting_not_found")
    item.text = text
    item.updated_by = updated_by
    await session.flush()
    return item


async def toggle_greeting(session: AsyncSession, greeting_id: int, updated_by: int | None) -> ChatGreeting:
    item = await session.get(ChatGreeting, greeting_id)
    if item is None:
        raise GreetingError("greeting_not_found")
    item.is_enabled = not item.is_enabled
    item.updated_by = updated_by
    await session.flush()
    return item
