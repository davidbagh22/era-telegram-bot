"""One-time editorial announcement for ERA's public channel."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.notification_service import safe_send_once
from app.services.book_club_service import PROGRAM_START

CHANNEL_POST = (
    "📚 <b>48 дней. 48 законов. Один книжный клуб.</b>\n\n"
    "В ЭРА начинаем читать и обсуждать «48 законов власти» Роберта Грина. "
    "Каждый день в 19:00 по Еревану будем разбирать по одному закону: "
    "что он означает, как проявляется в жизни и стоит ли с ним соглашаться.\n\n"
    "Без длинных лекций: короткий разбор, вопрос для обсуждения и задание. "
    "Выполняешь задание в боте — получаешь 5 баллов.\n\n"
    "Выпуски доступны в боте. Присоединяйся, даже если раньше не читал эту книгу. "
    "Если формат понравится, продолжим с другими произведениями.\n\n"
    "📖 Издание книги можно найти в каталоге Российской государственной библиотеки. "
    "В боте также есть ссылка на аудио.\n\n"
    "<b>ЭРА — это возможности, которыми делятся.</b>"
)


def channel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Читать и участвовать", url="https://t.me/ERA_1bot?start=literature")],
        [InlineKeyboardButton(text="📖 Найти книгу в РГБ", url="https://search.rsl.ru/ru/record/02000010666")],
    ])


def launch_window_open(day: date) -> bool:
    return PROGRAM_START <= day < PROGRAM_START + timedelta(days=48)

# A historical launch schedule is not new authorization for a channel post.
# Empty by default until an audited human approval of exact date/target/payload.
APPROVED_LITERATURE_CHANNEL_LAUNCHES: frozenset[tuple[str, str, str]] = frozenset()


def launch_approval_key(day: date, target: int | str) -> tuple[str, str, str]:
    payload = {
        "text": CHANNEL_POST,
        "keyboard": channel_keyboard().model_dump(mode="json", exclude_none=True),
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return (day.isoformat(), str(target), digest)


async def publish_literature_channel_launch(bot, settings):
    if not launch_window_open(datetime.now(ZoneInfo("Asia/Yerevan")).date()):
        return
    target = settings.era_channel_id or settings.era_channel_username
    if not target:
        return
    if isinstance(target, str) and not target.startswith("@") and not target.lstrip("-").isdigit():
        target = "@" + target
    if launch_approval_key(datetime.now(ZoneInfo("Asia/Yerevan")).date(), target) not in APPROVED_LITERATURE_CHANNEL_LAUNCHES:
        return
    await safe_send_once(
        bot, settings, target, CHANNEL_POST,
        delivery_key="era-literature-channel-launch-20261010",
        notification_type="literature_channel_launch",
        reply_markup=channel_keyboard(), parse_mode="HTML",
    )
