from aiogram import F, Bot, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import PointTransaction, Task, TaskSubmission, User
from app.services.notification_service import safe_send
from app.services.points_service import add_points
from app.utils import texts
from app.utils.constants import Role

router = Router(name="admin_task_guard2")


def is_admin(u: User | None, s: Settings, tg_id: int) -> bool:
    return bool(tg_id in s.admin_ids or (u and u.role == Role.ADMIN and not u.is_blocked))


@router.callback_query(F.data.startswith("admin:tasksub:approve:"))
async def approve_once(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    await call.answer()
    if not is_admin(user, settings, call.from_user.id):
        await call.message.answer(texts.NO_ACCESS)
        return
    submission = await session.get(TaskSubmission, int(call.data.rsplit(":", 1)[-1]))
    if not submission:
        await call.message.answer("Result not found")
        return
    task = await session.get(Task, submission.task_id)
    target = await session.get(User, submission.user_id)
    if not task or not target:
        await call.message.answer("Task or user not found")
        return
    if submission.status == "approved":
        await call.message.answer("Already approved")
        return
    previous = await session.scalar(
        select(PointTransaction).where(
            PointTransaction.user_id == target.id,
            PointTransaction.related_task_id == task.id,
            PointTransaction.points > 0,
        )
    )
    submission.status = "approved"
    submission.reviewed_by = user.id if user else None
    task.status = "completed"
    if previous:
        await call.message.answer("Approved without duplicate points")
        return
    await add_points(session, user_id=target.id, points=task.points, reason=f"Task completed: {task.title}", approved_by=user.id if user else None, related_task_id=task.id)
    await safe_send(bot, target.telegram_id, f"Task approved: {task.title}. Points: {task.points}")
    await call.message.answer("Approved and points added once")
