from datetime import datetime

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Task, User, UserDepartment, UserDirection
from app.services.audit_service import audit
from app.services.notification_service import safe_send
from app.states.task import TaskStates
from app.utils import texts
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role
from app.utils.telegram import send_long_text

router = Router(name="leader_addons")


async def _guard_call(call: CallbackQuery, user: User | None) -> bool:
    await call.answer()
    if not user or user.is_blocked or user.role not in PRIVILEGED_ROLES:
        await call.message.answer(texts.NO_ACCESS)
        return False
    return True


async def _guard_message(message: Message, user: User | None) -> bool:
    if not user or user.is_blocked or user.role not in PRIVILEGED_ROLES:
        await message.answer(texts.NO_ACCESS)
        return False
    return True


def _scope_ids(user: User) -> tuple[set[int], set[int]]:
    return (
        {item.department_id for item in user.departments},
        {item.direction_id for item in user.directions},
    )


def _tg(user: User) -> str:
    return f"@{user.username}" if user.username else str(user.telegram_id)


@router.message(TaskStates.points)
async def task_finish_serialized_deadline(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    if not await _guard_message(message, user):
        return
    try:
        points = int(message.text or "")
        if not 0 <= points <= 1000:
            raise ValueError
    except ValueError:
        await message.answer("Укажите число от 0 до 1000.")
        return
    data = await state.get_data()
    raw_deadline = data.get("task_deadline")
    if isinstance(raw_deadline, str):
        deadline = datetime.fromisoformat(raw_deadline)
    else:
        deadline = raw_deadline
    task = Task(
        title=data["task_title"],
        description=data["task_description"],
        assignee_id=data["task_assignee_id"],
        creator_id=user.id,
        deadline=deadline,
        points=points,
    )
    session.add(task)
    await session.flush()
    target = await session.get(User, task.assignee_id)
    if target:
        await safe_send(
            bot,
            target.telegram_id,
            f"У Вас новая задача ЭРА.\n\n{task.title}\n{task.description}\n\nДедлайн: {task.deadline:%d.%m.%Y %H:%M}",
        )
    await audit(
        session,
        actor_id=user.id,
        action="task.created",
        entity_type="task",
        entity_id=task.id,
    )
    await state.clear()
    await message.answer("Задача создана и отправлена исполнителю.")


@router.callback_query(F.data.in_({"leader:participants", "leader:tasks"}))
async def detailed_leader_participants(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard_call(call, user):
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
    participants = (
        await session.scalars(query.order_by(User.first_name, User.last_name))
    ).unique().all()
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
