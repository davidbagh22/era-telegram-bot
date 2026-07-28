from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Office, User, UserOffice
from app.services.audit_service import audit
from app.services.authorization_service import can_manage_people
from app.utils import texts

router = Router(name="admin_offices_management")


async def _guard(call: CallbackQuery, user: User | None, settings: Settings) -> bool:
    await call.answer()
    if not can_manage_people(user, settings, call.from_user.id):
        await call.message.answer(texts.NO_ACCESS)
        return False
    return True


def _office_keyboard(office_id: int, assignments: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="Назначить человека",
                callback_data=f"admin:office:assign:{office_id}",
            )
        ]
    ]
    for assignment_id, name in assignments:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Завершить: {name}"[:60],
                    callback_data=f"admin:office:remove:{assignment_id}",
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🗑 Удалить должность",
                    callback_data=f"admin:office:delete:{office_id}",
                )
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="admin:offices")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.regexp(r"^admin:office:view:\d+$"))
async def office_view(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    office = await session.get(Office, int(call.data.rsplit(":", 1)[-1]))
    if office is None or not office.is_active:
        await call.message.answer(
            "Эта должность уже удалена или недоступна",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="← К должностям", callback_data="admin:offices")]]
            ),
        )
        return

    assignments = (
        await session.scalars(
            select(UserOffice).where(
                UserOffice.office_id == office.id,
                UserOffice.is_active.is_(True),
            )
        )
    ).all()
    assignment_rows: list[tuple[int, str]] = []
    names: list[str] = []
    for assignment in assignments:
        target = await session.get(User, assignment.user_id)
        if target is None:
            continue
        name = f"{target.first_name} {target.last_name or ''}".strip()
        names.append(name)
        assignment_rows.append((assignment.id, name))

    await call.message.answer(
        f"{office.title}\n\n"
        f"{office.description or 'Описание можно добавить позже'}\n\n"
        f"Сейчас: {', '.join(names) or 'никто не назначен'}",
        reply_markup=_office_keyboard(office.id, assignment_rows),
    )


@router.callback_query(F.data.regexp(r"^admin:office:delete:\d+$"))
async def office_delete_confirm(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    office = await session.get(Office, int(call.data.rsplit(":", 1)[-1]))
    if office is None or not office.is_active:
        await call.message.answer("Эта должность уже удалена")
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, удалить",
                    callback_data=f"admin:office:delete_confirm:{office.id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="← Отмена",
                    callback_data=f"admin:office:view:{office.id}",
                )
            ],
        ]
    )
    await call.message.answer(
        f"Удалить должность «{office.title}»?\n\n"
        "Она исчезнет из активного списка. Текущие назначения будут завершены, а история сохранится.",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.regexp(r"^admin:office:delete_confirm:\d+$"))
async def office_delete(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    office = await session.get(Office, int(call.data.rsplit(":", 1)[-1]))
    if office is None or not office.is_active:
        await call.message.answer("Эта должность уже удалена")
        return

    active_assignments = (
        await session.scalars(
            select(UserOffice).where(
                UserOffice.office_id == office.id,
                UserOffice.is_active.is_(True),
            )
        )
    ).all()
    for assignment in active_assignments:
        assignment.is_active = False
        assignment.ends_at = date.today()

    office.is_active = False
    await audit(
        session,
        actor_id=user.id if user else None,
        action="office.deleted",
        entity_type="office",
        entity_id=office.id,
        old_value={"title": office.title, "active_assignments": len(active_assignments)},
        new_value={"is_active": False},
    )
    await call.message.answer(
        f"Должность «{office.title}» удалена. История назначений сохранена.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="← К должностям", callback_data="admin:offices")]]
        ),
    )
