"""One-time announcement for ERA's two existing team chats.

A recurring schedule does not authorize a new public announcement.
Delivery is idempotent and routed strictly to the Notifications forum topic.
"""
import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.general_topics_service import send_general_topic

EXTERNAL_INVITE = "https://t.me/+PsEYN685g1w5ZmEy"
INTERNAL_INVITE = "https://t.me/+zV8olVtkdc8yMWVi"

ANNOUNCEMENT = (
    "📢 <b>ЭРА | А ты уже в своём направлении?</b>\n\n"
    "В нашем объединении два направления — и каждое открывает свои возможности.\n\n"
    "🌍 <b>ВНЕШНИЕ СВЯЗИ</b>\n"
    "Международные проекты, форумы, конференции, партнёрства и новые знакомства. "
    "Здесь мы представляем ЭРА на внешних площадках и создаём возможности для сотрудничества.\n\n"
    "🏡 <b>ВНУТРЕННИЕ СВЯЗИ</b>\n"
    "Культурные встречи, мероприятия, волонтёрство, благотворительные акции, "
    "интерактивы и командные инициативы. Здесь идеи превращаются в события.\n\n"
    "✨ <b>Необязательно выбирать что-то одно!</b> "
    "Можно участвовать в обоих направлениях, предлагать идеи и находить своё место в команде.\n\n"
    "<b>ЭРА — это возможности, которыми делятся.</b>\n\n"
    "👇 Выбирай направление и присоединяйся!"
)


def directions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 Внешние связи", url=EXTERNAL_INVITE)],
        [InlineKeyboardButton(text="🏡 Внутренние связи", url=INTERNAL_INVITE)],
    ])


# Default deny until a responsible human approves the exact date, destination,
# HTML and buttons. Never derive consent from an old release or delivery key.
APPROVED_DIRECTIONS_ANNOUNCEMENTS: frozenset[tuple[str, str, str]] = frozenset()


def directions_approval_key(day: str, chat_id: int | str) -> tuple[str, str, str]:
    payload = {
        "text": ANNOUNCEMENT,
        "keyboard": directions_keyboard().model_dump(mode="json", exclude_none=True),
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return (day, str(chat_id), digest)


async def publish_directions_announcement(bot, settings) -> bool:
    target = settings.general_chat_id
    if target is None:
        return False
    day = datetime.now(ZoneInfo("Asia/Yerevan")).date().isoformat()
    if directions_approval_key(day, target) not in APPROVED_DIRECTIONS_ANNOUNCEMENTS:
        return False
    return await send_general_topic(
        bot, settings, "notifications", ANNOUNCEMENT,
        reply_markup=directions_keyboard(),
        delivery_key="era-directions-invite-v1",
        parse_mode="HTML",
    )
