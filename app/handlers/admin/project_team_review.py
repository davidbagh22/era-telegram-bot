from io import BytesIO
from aiogram import F, Bot, Router
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import Settings
from app.database.models import Project, User
from app.services.notification_service import safe_send
from app.services.project_builder import render_project_document
from app.utils import texts
from app.utils.constants import PROJECT_STATUS_LABELS, ProjectStatus, Role

router = Router(name="admin_project_team_review")

def ok(u: User | None, s: Settings, tg: int) -> bool:
    return bool(tg in s.admin_ids or (u and u.role == Role.ADMIN and not u.is_blocked))

async def g(call: CallbackQuery, user: User | None, settings: Settings) -> bool:
    await call.answer()
    if not ok(user, settings, call.from_user.id):
        await call.message.answer(texts.NO_ACCESS)
        return False
    return True

def project_kb(p: Project) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="📄 Полный файл проекта", callback_data=f"admin:project:file:{p.id}")]]
    rows.append([InlineKeyboardButton(text="✅ Принять / одобрить", callback_data=f"admin:project:review:{'venue_approve' if p.status == ProjectStatus.VENUE_REVIEW else 'initial_accept'}:{p.id}")])
    rows.append([InlineKeyboardButton(text="✏️ На доработку", callback_data=f"admin:project:review:revise:{p.id}")])
    rows.append([InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:project:review:reject:{p.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def document(p: Project, a: User | None) -> str:
    if p.generated_document:
        return p.generated_document
    name = f"{a.first_name} {a.last_name or ''}".strip() if a else f"ID {p.author_id}"
    tg = f"@{a.username}" if a and a.username else "без username"
    return render_project_document(p.form_data or {}, name, tg)

@router.callback_query(F.data == "admin:projects")
async def projects(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await g(call, user, settings):
        return
    items = (await session.scalars(select(Project).where(Project.status.in_([ProjectStatus.PENDING_REVIEW, ProjectStatus.INITIAL_REVIEW, ProjectStatus.VENUE_REVIEW])).order_by(Project.submitted_at, Project.created_at))).all()
    if not items:
        await call.message.answer("Проектов на рассмотрении нет")
        return
    for p in items:
        a = await session.get(User, p.author_id)
        who = f"{a.first_name} {a.last_name or ''}".strip() if a else f"ID {p.author_id}"
        tg = f"@{a.username}" if a and a.username else "без username"
        await call.message.answer(f"💡 Проект #{p.id}\n\n{p.title}\n\nАвтор: {who} ({tg})\nСтатус: {PROJECT_STATUS_LABELS.get(p.status, p.status)}\n\nСуть:\n{p.short_description}", reply_markup=project_kb(p))

@router.callback_query(F.data.startswith("admin:project:file:"))
async def project_file(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await g(call, user, settings):
        return
    p = await session.get(Project, int(call.data.rsplit(":", 1)[-1]))
    if not p:
        await call.message.answer("Проект не найден")
        return
    a = await session.get(User, p.author_id)
    text = await document(p, a)
    p.generated_document = text
    await call.message.answer_document(BufferedInputFile(BytesIO(text.encode("utf-8")).getvalue(), filename=f"ERA_project_{p.id}.txt"), caption=f"Полный проект #{p.id}: {p.title}")

@router.callback_query(F.data.regexp(r"^admin:team_post:(approve|reject):\d+$"))
async def team_post_review(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await g(call, user, settings):
        return
    _, _, action, raw_project_id = call.data.split(":")
    project = await session.get(Project, int(raw_project_id))
    if not project:
        await call.message.answer("Проект не найден")
        return
    author = await session.get(User, project.author_id)
    data = dict(project.form_data or {})
    text = data.get("team_search_post")
    if not text:
        await call.message.answer("Текст публикации не найден")
        return
    data["team_search_status"] = "rejected" if action == "reject" else "approved"
    project.form_data = data
    if action == "reject":
        if author:
            await safe_send(bot, author.telegram_id, f"Публикация для поиска команды по проекту «{project.title}» отклонена.")
        await call.message.answer("Публикация отклонена")
        return
    if settings.general_chat_id:
        await safe_send(bot, settings.general_chat_id, f"🔍 Команда для проекта ЭРА\n\n{project.title}\n\n{text}")
    if author:
        await safe_send(bot, author.telegram_id, f"Публикация для поиска команды по проекту «{project.title}» одобрена.")
    await call.message.answer("Публикация одобрена и отправлена в общий чат, если он подключён.")
