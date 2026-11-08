"""Media hub entry in the native administrator panel; read-only forum inspection."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.database.media_models import MediaContentItem
from app.services.admin_dashboard_service import has_dashboard_access
from app.services.media_service import media_access_level, media_permissions
from app.services.media_topics_service import TOPICS, read_topics, topic_links
from app.utils import texts

router = Router(name="admin_native_media")


async def show_media(message: Message, user: User | None, settings: Settings, session: AsyncSession) -> None:
    level = await media_access_level(session, user, settings)
    permissions = media_permissions(level)
    chat_id = settings.media_chat_id
    rows = []
    status = "Чат пока не привязан к боту."
    if chat_id:
        registry = await read_topics(session, chat_id)
        links = {entry["key"]: entry["url"] for entry in await topic_links(session, chat_id)}
        ready = len(links)
        status = f"Темы: {ready}/{len(TOPICS)} готовы."
        for key, name in TOPICS.items():
            if key in links:
                rows.append([InlineKeyboardButton(text=name, url=links[key])])
            else:
                item = registry.get(key, {})
                state = item.get("state", "не настроена") if isinstance(item, dict) else "нужна проверка"
                rows.append([InlineKeyboardButton(text=f"⚠ {name} · {str(state)[:24]}", callback_data="admin:media:refresh")])
    rows.insert(0, [InlineKeyboardButton(text="📋 Очередь материалов", callback_data="admin:media:queue")])
    rows.append([InlineKeyboardButton(text="🔄 Обновить состояние", callback_data="admin:media:refresh")])
    rows.append([InlineKeyboardButton(text="← Админ-панель", callback_data="admin:panel")])
    counts = dict((await session.execute(select(MediaContentItem.status, func.count(MediaContentItem.id))
                                  .group_by(MediaContentItem.status))).all())
    description = ("Контент-план: " + str(sum(counts.values())) + " материалов. "
                   + "На согласовании: " + str(counts.get("review", 0)) + ". "
                   + "Готово: " + str(counts.get("ready", 0)) + ". "
                   + "Запланировано: " + str(counts.get("scheduled", 0)) + ".\n\n"
                   + "Для редактирования материалов откройте раздел «Медиа» в приложении ЭРА. "
                   + "Ссылки ниже ведут только в подтверждённые темы чата.")
    await message.answer(
        f"🎬 <b>Медиа ЭРА</b>\n\n{status}\n"
        f"Роль: {'руководитель' if permissions.get('publications_manage') else 'участник / просмотр'}\n\n"
        + description,
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.message(Command("media_admin"))
async def media_command(message: Message, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not has_dashboard_access(user, settings, message.from_user.id):
        await message.answer(texts.NO_ACCESS)
        return
    await show_media(message, user, settings, session)


@router.callback_query(F.data.in_({"admin:media", "admin:media:refresh"}))
async def media_callback(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not has_dashboard_access(user, settings, call.from_user.id):
        await call.answer(texts.NO_ACCESS, show_alert=True)
        return
    await call.answer()
    await show_media(call.message, user, settings, session)


@router.callback_query(F.data == "admin:media:queue")
async def media_queue(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not has_dashboard_access(user, settings, call.from_user.id):
        await call.answer(texts.NO_ACCESS, show_alert=True)
        return
    await call.answer()
    items = (await session.scalars(select(MediaContentItem)
        .where(MediaContentItem.status.in_(("review", "ready", "scheduled", "failed")))
        .order_by(MediaContentItem.id.desc()).limit(12))).all()
    labels = {"review": "На согласовании", "ready": "Готово",
              "scheduled": "Запланировано", "failed": "Ошибка публикации"}
    body = "📋 Медиа · рабочая очередь\n\n"
    if items:
        body += "\n".join(f"#{item.id} · {labels.get(item.status, item.status)} · "
                          f"{(item.title or item.rubric or 'Материал')[:100]}" for item in items)
    else:
        body += "Нет материалов, ожидающих действия."
    body += "\n\nЭто обзор без изменений и автоматической публикации."
    await call.message.answer(body, parse_mode=None, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩ Медиа", callback_data="admin:media")],
    ]))
