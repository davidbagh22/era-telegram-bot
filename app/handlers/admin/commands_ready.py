from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Office, PositionApplication, User, UserOffice
from app.handlers.admin.access import guard_admin_bot as _guard
from app.keyboards.participant import open_app_button
from app.services.system_health_service import system_snapshot
from app.utils import texts
from app.utils.constants import ApplicationStatus, PositionApplicationStatus

router = Router(name="admin_commands_ready")
router.message.filter(F.chat.type == "private")


async def _redirect(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    await message.answer(texts.ADMIN_PANEL_MOVED, reply_markup=open_app_button(settings.effective_miniapp_url))


def _ops_keyboard(active: str = "status") -> InlineKeyboardMarkup:
    def label(key: str, text: str) -> str:
        return f"• {text}" if key == active else text
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=label("status", "Система"), callback_data="admin:ops:status"),
            InlineKeyboardButton(text=label("backup", "Backup"), callback_data="admin:ops:backup"),
            InlineKeyboardButton(text=label("org", "Организация"), callback_data="admin:ops:org"),
        ],
        [InlineKeyboardButton(text="↻ Обновить", callback_data=f"admin:ops:{active}:refresh")],
    ])


def _status_text(snapshot: dict) -> str:
    latest = snapshot.get("latest") or {}
    incidents = [item for item in snapshot.get("incidents", []) if item.get("status") == "open"]
    critical = [item for item in incidents if item.get("severity") in {"critical", "high"}]
    checks = latest.get("checks") or []
    failed_checks = [item for item in checks if item.get("status") != "ok"]
    check_lines = []
    for item in checks[:12]:
        name = str(item.get("name") or item.get("check") or "check")
        status = str(item.get("status") or "unknown")
        check_lines.append(f"{'✅' if status == 'ok' else '⚠️'} {name}: {status}")
    details = "\n".join(check_lines) if check_lines else "Проверки: нет данных"
    return (
        "Система ЭРА\n\n"
        f"Состояние: {latest.get('status', 'нет данных')}\n"
        f"Health: {latest.get('score', '—')}/100\n"
        f"Открытых инцидентов: {len(incidents)}\n"
        f"Высокой критичности: {len(critical)}\n"
        f"Проверок с отклонением: {len(failed_checks)}\n"
        f"Commit: {(latest.get('commit_sha') or 'unknown')[:12]}\n\n"
        f"{details}"
    )


def _backup_text(snapshot: dict) -> str:
    backups = snapshot.get("backups") or []
    if not backups:
        return "Backup ЭРА\n\nВ BackupHistory пока нет подтверждённых записей."
    latest = backups[0]
    return (
        "Backup ЭРА\n\n"
        f"Статус: {latest.get('status', 'unknown')}\n"
        f"Тип: {latest.get('backup_type') or '—'}\n"
        f"Хранилище: {latest.get('storage_provider') or '—'}\n"
        f"Завершён: {latest.get('completed_at') or latest.get('created_at') or '—'}\n"
        f"Размер: {latest.get('size_bytes') or '—'}\n"
        f"Commit: {(latest.get('commit_sha') or '—')[:12]}\n"
        f"Restore verification: {latest.get('restore_verified_at') or 'нет'}\n"
        f"История: {len(backups)} последних записей"
    )


async def _org_text(session: AsyncSession) -> str:
    users = int(await session.scalar(select(func.count(User.id))) or 0)
    pending = int(await session.scalar(select(func.count(User.id)).where(User.application_status == ApplicationStatus.PENDING)) or 0)
    offices = int(await session.scalar(select(func.count(Office.id)).where(Office.is_active.is_(True))) or 0)
    assignments = int(await session.scalar(select(func.count(UserOffice.id)).where(UserOffice.is_active.is_(True))) or 0)
    vacancies = int(await session.scalar(select(func.count(Office.id)).where(Office.is_active.is_(True), Office.is_public.is_(True), Office.application_enabled.is_(True))) or 0)
    position_apps = int(await session.scalar(select(func.count(PositionApplication.id)).where(PositionApplication.status.in_([
        PositionApplicationStatus.SUBMITTED,
        PositionApplicationStatus.REVIEWING,
        "needs_info",
        PositionApplicationStatus.INTERVIEW,
        PositionApplicationStatus.RESERVE,
        PositionApplicationStatus.APPROVED,
    ]))) or 0)
    return (
        "Организация ЭРА\n\n"
        f"Профилей: {users}\n"
        f"Заявок на вступление: {pending}\n"
        f"Активных должностей: {offices}\n"
        f"Текущих назначений: {assignments}\n"
        f"Открытых вакансий: {vacancies}\n"
        f"Активных заявок на роли: {position_apps}"
    )


async def _send_status(message: Message, session: AsyncSession) -> None:
    await message.answer(_status_text(await system_snapshot(session)), reply_markup=_ops_keyboard("status"))


async def _send_backup(message: Message, session: AsyncSession) -> None:
    await message.answer(_backup_text(await system_snapshot(session)), reply_markup=_ops_keyboard("backup"))


async def _send_org(message: Message, session: AsyncSession) -> None:
    await message.answer(await _org_text(session), reply_markup=_ops_keyboard("org"))


async def _edit_ops(call: CallbackQuery, text: str, active: str) -> None:
    if call.message and call.message.text == text:
        await call.answer("Данные актуальны")
        return
    if call.message:
        await call.message.edit_text(text, reply_markup=_ops_keyboard(active))
    await call.answer()


@router.message(Command("status"))
async def status_command(message: Message, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if await _guard(message, user, settings):
        await _send_status(message, session)


@router.message(Command("backup"))
async def backup_command(message: Message, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if await _guard(message, user, settings):
        await _send_backup(message, session)


@router.message(Command("org"))
async def org_command(message: Message, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if await _guard(message, user, settings):
        await _send_org(message, session)


@router.callback_query(F.data.in_({"admin:ops:status", "admin:ops:status:refresh"}))
async def status_callback(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    await _edit_ops(call, _status_text(await system_snapshot(session)), "status")


@router.callback_query(F.data.in_({"admin:ops:backup", "admin:ops:backup:refresh"}))
async def backup_callback(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    await _edit_ops(call, _backup_text(await system_snapshot(session)), "backup")


@router.callback_query(F.data.in_({"admin:ops:org", "admin:ops:org:refresh"}))
async def org_callback(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    await _edit_ops(call, await _org_text(session), "org")


@router.message(Command("admin_users"))
async def admin_users_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await _redirect(message, user, settings, state)


@router.message(Command("admin_events"))
async def admin_events_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await _redirect(message, user, settings, state)


@router.message(Command("admin_projects"))
async def admin_projects_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await _redirect(message, user, settings, state)


@router.message(Command("admin_partners"))
async def admin_partners_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await _redirect(message, user, settings, state)


@router.message(Command("admin_tasks"))
async def admin_tasks_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await _redirect(message, user, settings, state)


@router.message(Command("admin_rights"))
async def admin_rights_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await _redirect(message, user, settings, state)
