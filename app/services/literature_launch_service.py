"""One-time book-club opening, safely retried until delivered in the forum."""
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.book_club_service import daily_job
from app.services.general_topics_service import ensure_topic, send_general_topic

ANNOUNCEMENT = (
    "📚 <b>В ЭРА начинается новая история: читаем вместе!</b>\n\n"
    "Открываем литературный клуб. Первой книгой станет "
    "<b>«48 законов власти» Роберта Грина</b>.\n\n"
    "48 выпусков, 48 поводов подумать и обсудить идеи с единомышленниками. "
    "В каждом выпуске — краткий разбор, вопрос для обсуждения и задание. "
    "За выполнение задания в боте начисляются 5 баллов.\n\n"
    "📅 <b>Первый выпуск — сегодня, 10 октября.</b> "
    "Дальше читаем по понедельникам, средам и пятницам в 19:00 по Еревану.\n\n"
    "💬 Обсуждения — в теме <b>«Литература»</b> нашего общего чата. "
    "А в боте можно подписаться на выпуски и отмечать прогресс.\n\n"
    "Начнём с этой книги. Если формат понравится, будем читать другие вместе!"
)


def launch_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Открыть литературу в боте", url="https://t.me/ERA_1bot?start=literature")],
    ])


async def publish_literature_launch(bot, settings, session_factory):
    # Retry only on the exceptional opening day; never replay this opening later.
    if datetime.now(ZoneInfo("Asia/Yerevan")).date().isoformat() != "2026-10-10":
        return
    topic_id = await ensure_topic(bot, settings, "literature")
    if topic_id is None:
        return
    # The normal scheduled issue uses its own durable key, so reruns are safe.
    await daily_job(bot, settings, session_factory)
    await send_general_topic(
        bot, settings, "notifications", ANNOUNCEMENT,
        reply_markup=launch_keyboard(),
        delivery_key="era-literature-launch-20261010", parse_mode="HTML",
    )
