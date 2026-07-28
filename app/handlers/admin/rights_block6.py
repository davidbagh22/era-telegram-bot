from __future__ import annotations

from datetime import datetime

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import PermissionGrant, User
from app.keyboards.participant import main_menu
from app.services.audit_service import audit
from app.services.authorization_service import (
    can_change_access_status,
    can_change_permission,
    can_change_role,
    can_manage_people,
    can_manage_permissions,
    can_view_people,
)
from app.services.notification_service import safe_send
from app.services.admin_user_card import send_admin_user_card
from app.utils import texts
from app.utils.constants import (
    PERMISSIONS,
    PRIVILEGED_ROLES,
    ROLE_LABELS,
    STATUS_LABELS,
    ParticipationStatus,
    Role,
)

router = Router(name="admin_rights_block6")


def _role_label(value: str | Role | None) -> str:
    try:
        return ROLE_LABELS[Role(value)]
    except Exception:
        return str(value or "не указана")


def _status_label(value: str | ParticipationStatus | None) -> str:
    try:
        return STATUS_LABELS[ParticipationStatus(value)]
    except Exception:
        return str(value or "не указан")


async def _guard(
    event: CallbackQuery | Message,
    user: User | None,
    settings: Settings,
    *,
    manage: bool = False,
    permissions: bool = False,
) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
        telegram_id = event.from_user.id
    else:
        message = event
        telegram_id = event.from_user.id
    allowed = (
        can_manage_permissions(user, settings, telegram_id)
        if permissions
        else can_manage_people(user, settings, telegram_id)
        if manage
        else can_view_people(user, settings, telegram_id)
    )
    if not allowed:
        await message.answer(texts.NO_ACCESS)
        return False
    return True


def _user_actions(target: User) -> InlineKeyboardMarkup:
    block_label = "✅ Разблокировать" if target.is_blocked else "🚫 Заблокировать"
    block_action = "unblock" if target.is_blocked else "block"
    archive_label = "↩️ Вернуть из архива" if target.is_archived else "🗄 В архив"
    archive_action = "unarchive" if target.is_archived else "archive"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Баллы", callback_data=f"admin:user:points:{target.id}"),
                InlineKeyboardButton(text="🏅 Знак", callback_data=f"admin:user:badge:{target.id}"),
            ],
            [
                InlineKeyboardButton(text="Изменить роль", callback_data=f"admin:user:role:{target.id}"),
                InlineKeyboardButton(text="Изменить статус", callback_data=f"admin:user:status:{target.id}"),
            ],
            [
                InlineKeyboardButton(text="🔐 Технические права", callback_data=f"admin:user:permissions:{target.id}"),
            ],
            [
                InlineKeyboardButton(text=block_label, callback_data=f"admin:user:{block_action}:{target.id}"),
                InlineKeyboardButton(text=archive_label, callback_data=f"admin:user:{archive_action}:{target.id}"),
            ],
            [InlineKeyboardButton(text="Портфолио", callback_data=f"admin:user:portfolio:{target.id}")],
            [InlineKeyboardButton(text="← К списку", callback_data="admin:participants")],
        ]
    )


def _role_keyboard(target_id: int) -> InlineKeyboardMarkup:
    options = (
        (Role.PARTICIPANT, "Участник"),
        (Role.ACTIVIST, "Активист"),
        (Role.LEADER, "Лидер"),
        (Role.HEAD, "Руководитель направления"),
        (Role.COUNCIL, "Совет"),
        (Role.ADMIN, "Админ"),
    )
    rows = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=f"admin:user:setrole:{target_id}:{role.value}",
            )
        ]
        for role, label in options
    ]
    rows.append([InlineKeyboardButton(text="← К участнику", callback_data=f"admin:user:{target_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _permissions_keyboard(target_id: int, active: set[str]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'✅' if permission in active else '▫️'} {PERMISSION_LABELS.get(permission, permission)}",
                callback_data=f"admin:permission:toggle:{target_id}:{permission}",
            )
        ]
        for permission in PERMISSIONS
    ]
    rows.append([InlineKeyboardButton(text="← К участнику", callback_data=f"admin:user:{target_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.regexp(r"^admin:user:\d+$"))
async def user_card(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.clear()
    target = await session.get(User, int(call.data.rsplit(":", 1)[-1]))
    if not target:
        await call.message.answer("Участник не найден")
        return
    await send_admin_user_card(call.message, session, target, mode="profile")


@router.callback_query(F.data.regexp(r"^admin:user:role:\d+$"))
async def role_menu(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    if not await _guard(call, user, settings, manage=True):
        return
    target_id = int(call.data.rsplit(":", 1)[-1])
    await call.message.answer("Выберите роль участника", reply_markup=_role_keyboard(target_id))


@router.callback_query(F.data.regexp(r"^admin:user:setrole:\d+:[a-z_]+$"))
async def set_role(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings, manage=True):
        return
    _, _, _, raw_target, raw_role = call.data.split(":")
    try:
        new_role = Role(raw_role)
    except ValueError:
        await call.message.answer("Такой роли нет")
        return
    target = await session.get(User, int(raw_target))
    if not target:
        await call.message.answer("Участник не найден")
        return
    decision = await can_change_role(
        session,
        actor=user,
        actor_telegram_id=call.from_user.id,
        target=target,
        new_role=new_role,
        settings=settings,
    )
    if not decision.allowed:
        await call.message.answer(decision.reason)
        return
    old_role = target.role
    target.role = new_role.value
    await audit(
        session,
        actor_id=user.id if user else None,
        action="user.role_changed",
        entity_type="user",
        entity_id=target.id,
        old_value={"role": old_role},
        new_value={"role": new_role.value},
    )
    await call.message.answer(f"Роль обновлена: {_role_label(new_role)}")
    await safe_send(
        bot,
        target.telegram_id,
        f"Ваша роль в ЭРА обновлена: {_role_label(new_role)}\n\nНовые возможности уже доступны в меню",
        main_menu(
            settings.era_channel_url,
            privileged=new_role in PRIVILEGED_ROLES,
            admin=new_role == Role.ADMIN,
        ),
    )


@router.callback_query(F.data.regexp(r"^admin:user:permissions:\d+$"))
@router.callback_query(F.data.regexp(r"^admin:permissions:user:\d+$"))
async def permissions_menu(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings, permissions=True):
        return
    await state.clear()
    target_id = int(call.data.rsplit(":", 1)[-1])
    target = await session.get(User, target_id)
    if not target:
        await call.message.answer("Участник не найден")
        return
    grants = (
        await session.scalars(
            select(PermissionGrant).where(
                PermissionGrant.user_id == target_id,
                PermissionGrant.scope_type == "global",
                PermissionGrant.scope_id == 0,
            )
        )
    ).all()
    active = {grant.permission for grant in grants if grant.is_active}
    await call.message.answer(
        f"🔐 Технические права\n\n{target.first_name} {target.last_name or ''}\n\n"
        "Нажимайте на право, чтобы включать или отключать его. Изменения работают сразу, без перезапуска бота",
        reply_markup=_permissions_keyboard(target_id, active),
    )


@router.callback_query(F.data.regexp(r"^admin:permission:toggle:\d+:.+$"))
async def permission_toggle(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings, permissions=True):
        return
    _, _, _, raw_target, permission = call.data.split(":", 4)
    if permission not in PERMISSIONS:
        await call.message.answer("Такого права нет")
        return
    target_id = int(raw_target)
    target = await session.get(User, target_id)
    if not target:
        await call.message.answer("Участник не найден")
        return
    decision = await can_change_permission(actor=user, target=target)
    if not decision.allowed:
        await call.message.answer(decision.reason)
        return
    grant = await session.scalar(
        select(PermissionGrant).where(
            PermissionGrant.user_id == target_id,
            PermissionGrant.permission == permission,
            PermissionGrant.scope_type == "global",
            PermissionGrant.scope_id == 0,
        )
    )
    if grant:
        grant.is_active = not grant.is_active
        enabled = grant.is_active
    else:
        session.add(
            PermissionGrant(
                user_id=target_id,
                permission=permission,
                scope_type="global",
                scope_id=0,
                granted_by=user.id if user else target_id,
            )
        )
        enabled = True
    await audit(
        session,
        actor_id=user.id if user else None,
        action="user.permission_changed",
        entity_type="user",
        entity_id=target_id,
        new_value={"permission": permission, "enabled": enabled},
    )
    await call.message.answer(
        f"{'Включено' if enabled else 'Отключено'}: {PERMISSION_LABELS.get(permission, permission)}"
    )


@router.callback_query(F.data.regexp(r"^admin:user:(block|unblock):\d+$"))
async def block_toggle(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings, manage=True):
        return
    _, _, action, raw_target = call.data.split(":")
    target = await session.get(User, int(raw_target))
    if not target:
        await call.message.answer("Участник не найден")
        return
    decision = await can_change_access_status(
        session, actor=user, target=target, settings=settings
    )
    if not decision.allowed:
        await call.message.answer(decision.reason)
        return
    target.is_blocked = action == "block"
    await audit(
        session,
        actor_id=user.id if user else None,
        action=f"user.{action}",
        entity_type="user",
        entity_id=target.id,
    )
    await call.message.answer("Участник заблокирован" if target.is_blocked else "Участник разблокирован")


@router.callback_query(F.data.regexp(r"^admin:user:(archive|unarchive):\d+$"))
async def archive_toggle(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings, manage=True):
        return
    _, _, action, raw_target = call.data.split(":")
    target = await session.get(User, int(raw_target))
    if not target:
        await call.message.answer("Участник не найден")
        return
    decision = await can_change_access_status(
        session, actor=user, target=target, settings=settings
    )
    if not decision.allowed:
        await call.message.answer(decision.reason)
        return
    if action == "archive":
        target.is_archived = True
        target.archived_at = datetime.now().astimezone()
        target.archived_by = user.id if user else None
        text = "Участник перемещён в архив"
    else:
        target.is_archived = False
        target.archived_at = None
        target.archived_by = None
        text = "Участник возвращён из архива"
    await audit(
        session,
        actor_id=user.id if user else None,
        action=f"user.{action}",
        entity_type="user",
        entity_id=target.id,
    )
    await call.message.answer(text)
