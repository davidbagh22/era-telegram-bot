from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, UserDepartment, UserDirection
from app.utils import texts
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role
from app.utils.telegram import send_long_text

router = Router(name="leader_addons")


async def _guard(call: CallbackQuery, user: User | None) -> bool:
    await call.answer()
    if not user or user.is_blocked or user.role not in PRIVILEGED_ROLES:
        await call.message.answer(texts.NO_ACCESS)
        return False
    return True


def _scope_ids(user: User) -> tuple[set[int], set[int]]:
    return (
        {item.department_id for item in user.departments},
        {item.direction_id for item in user.directions},
    )


def _tg(user: User) -> str:
    return f"@{user.username}" if user.username else str(user.telegram_id)


@router.callback_query(F.data.in_({"leader:participants", "leader:tasks"}))
async def detailed_leader_participants(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    if user.role == Role.ADMIN:
        query = select(User).where(
            User.application_status == ApplicationStatus.APPROVED,
            User.is_archived.is_(False),
        )
    else:
        department_ids, direction_ids = _scope_ids(user)
        query = (
            select(User)
            .outerjoin(UserDepartment)
            .outerjoin(UserDirection)
            .where(
                User.application_status == ApplicationStatus.APPROVED,
                User.is_archived.is_(False),
                or_(
                    UserDepartment.department_id.in_(department_ids or {-1}),
                    UserDirection.direction_id.in_(direction_ids or {-1}),
                ),
            )
        )
    participants = (await session.scalars(query.order_by(User.first_name, User.last_name))).unique().all()
    if not participants:
        await call.message.answer("В Вашем направлении пока нет активистов.")
        return
    blocks = []
    for item in participants:
        departments = ", ".join(rel.department.name for rel in item.departments) or "не выбраны"
        directions = ", ".join(rel.direction.name for rel in item.directions) or "не выбраны"
        blocks.append(
            f"👤 {item.first_name} {item.last_name or ''}\n"
            f"Возраст: {item.age or 'не указан'}\n"
            f"Город: {item.city or 'не указан'}\n"
            f"Телефон: {item.phone or 'не указан'}\n"
            f"Telegram: {_tg(item)}\n"
            f"Email: {item.email or 'не указан'}\n"
            f"Департаменты: {departments}\n"
            f"Направления: {directions}"
        )
    await send_long_text(
        call.message,
        "👥 Активисты по Вашему направлению\n\n" + "\n\n".join(blocks),
    )
