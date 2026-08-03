from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.keyboards.admin import admin_panel_keyboard
from app.services.admin_dashboard_service import DashboardMetrics, dashboard_metrics, has_dashboard_access
from app.utils import texts

router = Router(name="admin_dashboard_block_a")


async def _guard(event: Message | CallbackQuery, user: User | None, settings: Settings) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
        telegram_id = event.from_user.id
    else:
        message = event
        telegram_id = event.from_user.id
    if not has_dashboard_access(user, settings, telegram_id):
        await message.answer(texts.NO_ACCESS)
        return False
    return True


def _dashboard_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🧭 Что где ждёт", callback_data="admin:attention")]]
    rows.extend(admin_panel_keyboard().inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _dashboard_text(metrics: DashboardMetrics) -> str:
    m = metrics.values
    attention = metrics.attention_total
    return (
        "⚙️ Админ-панель ЭРА\n\n"
        "Организация сейчас:\n"
        f"👥 Участники всего: {m['users_total']}\n"
        f"✅ Одобрены: {m['users_approved']}\n"
        f"📝 Новые заявки: {m['users_pending']}\n"
        f"🔥 Активисты: {m['activists']}\n"
        f"🧭 Лидеры / совет / админы: {m['leaders']}\n\n"
        "Проекты и события:\n"
        f"💡 Проекты на проверке: {m['projects_review']}\n"
        f"🚀 Активные проекты: {m['projects_active']}\n"
        f"📅 Мероприятия на согласовании: {m['events_pending']}\n"
        f"📣 Мероприятия в работе / опубликованы: {m['events_live']}\n\n"
        "Что ждёт решения:\n"
        f"✅ Итоги заданий: {m['task_results']}\n"
        f"✨ Активности после мероприятий: {m['activity_results']}\n"
        f"🎁 Заявки на возможности: {m['rewards']}\n"
        f"🎓 Портфолио: {m['portfolio']}\n"
        f"📄 Отчёты: {m['reports']}\n"
        f"💬 Вопросы: {m['questions']}\n"
        f"🏛 Заявки по направлениям: {m['departments']}\n\n"
        f"Итого требует внимания: {attention}\n"
        f"Открытых задач в системе: {m['tasks_open']}"
    )


@router.message(Command("admin"))
@router.message(F.text == "⚙️ Управление")
async def admin_dashboard(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    metrics = await dashboard_metrics(session)
    await message.answer(_dashboard_text(metrics), reply_markup=_dashboard_keyboard())


@router.callback_query(F.data == "admin:panel")
async def admin_dashboard_callback(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.clear()
    metrics = await dashboard_metrics(session)
    await call.message.answer(_dashboard_text(metrics), reply_markup=_dashboard_keyboard())


@router.callback_query(F.data == "admin:attention")
async def admin_attention(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    m = (await dashboard_metrics(session)).values
    items = [
        ("📝 Новые заявки", "admin:applications", m["users_pending"]),
        ("💡 Проекты", "admin:projects", m["projects_review"]),
        ("📅 Мероприятия", "admin:events", m["events_pending"]),
        ("✅ Итоги заданий", "admin:task_submissions", m["task_results"]),
        ("✨ Активности", "admin:event_activities:review", m["activity_results"]),
        ("🎁 Возможности", "admin:reward:redemptions", m["rewards"]),
        ("🎓 Портфолио", "admin:portfolio", m["portfolio"]),
        ("📄 Отчёты", "admin:reports", m["reports"]),
        ("💬 Вопросы", "admin:questions", m["questions"]),
        ("🏛 Направления", "admin:departments", m["departments"]),
    ]
    rows: list[list[InlineKeyboardButton]] = []
    lines = ["🧭 Что где ждёт\n"]
    for label, callback, amount in items:
        lines.append(f"{label}: {amount}")
        if amount:
            rows.append([InlineKeyboardButton(text=f"{label} · {amount}", callback_data=callback)])
    rows.append([InlineKeyboardButton(text="← Админ-панель", callback_data="admin:panel")])
    await call.message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
