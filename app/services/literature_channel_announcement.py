"""One-time editorial announcement for ERA's public channel."""
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.notification_service import safe_send_once

CHANNEL_POST = (
    "📚 <b>48 дней. 48 законов. Один книжный клуб.</b>\n\n"
    "В ЭРА начинаем читать и обсуждать «48 законов власти» Роберта Грина. "
    "Каждый день в 19:00 по Еревану будем разбирать по одному закону: "
    "что он означает, как проявляется в жизни и стоит ли с ним соглашаться.\n\n"
    "Без длинных лекций: короткий разбор, вопрос для обсуждения и задание. "
    "Выполняешь задание в боте — получаешь 5 баллов.\n\n"
    "Первый выпуск уже сегодня. Присоединяйся, даже если раньше не читал эту книгу. "
    "Если формат понравится, продолжим с другими произведениями.\n\n"
    "📖 PDF/DJVU доступен на стороннем сайте Sci.ru; статус прав на файл не подтверждён. "
    "В боте также есть ссылка на аудио.\n\n"
    "<b>ЭРА — это возможности, которыми делятся.</b>"
)


def channel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Читать и участвовать", url="https://t.me/ERA_1bot?start=literature")],
        [InlineKeyboardButton(text="📖 PDF/DJVU · Sci.ru", url="https://sci.ru/disk/file/19957")],
    ])


async def publish_literature_channel_launch(bot, settings):
    if datetime.now(ZoneInfo("Asia/Yerevan")).date().isoformat() != "2026-10-10":
        return
    target = settings.era_channel_id or settings.era_channel_username
    if not target:
        return
    if isinstance(target, str) and not target.startswith("@") and not target.lstrip("-").isdigit():
        target = "@" + target
    await safe_send_once(
        bot, settings, target, CHANNEL_POST,
        delivery_key="era-literature-channel-launch-20261010",
        notification_type="literature_channel_launch",
        reply_markup=channel_keyboard(), parse_mode="HTML",
    )
