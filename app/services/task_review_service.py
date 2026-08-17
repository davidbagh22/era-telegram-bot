from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PointTransaction, Task, TaskParticipant, TaskSubmission, User
from app.services.activity_scoring_service import score_task_completion
from app.utils.constants import TaskStatus

TASK_REVIEW_ACTIONS = ("approve", "revision", "reject")


@dataclass(frozen=True)
class TaskReviewResult:
    submission: TaskSubmission
    admin_notice: str
    participant_notice: str | None
    points_awarded: int


async def list_pending_submissions(session: AsyncSession) -> list[TaskSubmission]:
    rows = await session.scalars(
        select(TaskSubmission)
        .where(TaskSubmission.status == "pending")
        .order_by(TaskSubmission.created_at.desc())
        .limit(30)
    )
    return list(rows.all())


async def _already_awarded(session: AsyncSession, user_id: int, task_id: int) -> bool:
    """Compatibility guard for tasks paid by the pre-scoring implementation."""
    previous = await session.scalar(
        select(PointTransaction).where(
            PointTransaction.user_id == user_id,
            PointTransaction.related_task_id == task_id,
            PointTransaction.points > 0,
        )
    )
    return previous is not None


async def decide_submission(
    session: AsyncSession,
    submission: TaskSubmission,
    task: Task,
    participant: User,
    *,
    action: str,
    comment: str,
    actor: User,
) -> TaskReviewResult:
    if action not in TASK_REVIEW_ACTIONS:
        raise ValueError(f"unknown task review action: {action!r}")
    if action in ("revision", "reject") and not comment.strip():
        raise ValueError("comment_required")

    if action == "approve":
        if submission.status == "approved":
            return TaskReviewResult(
                submission=submission,
                admin_notice="Этот результат уже одобрен. Повторно баллы не начисляются.",
                participant_notice=None,
                points_awarded=0,
            )
        submission.status = "approved"
        submission.reviewed_by = actor.id
        if await _already_awarded(session, participant.id, task.id):
            return TaskReviewResult(
                submission=submission,
                admin_notice="Результат принят. Баллы за это задание уже начислялись ранее.",
                participant_notice=None,
                points_awarded=0,
            )

        transaction = await score_task_completion(
            session,
            task,
            participant,
            submission_id=submission.id,
            approved_by_id=actor.id,
        )
        awarded_points = int(transaction.points)

        if task.task_type == "private":
            task.status = TaskStatus.COMPLETED
        else:
            member_ids = set(
                (
                    await session.scalars(
                        select(TaskParticipant.user_id).where(
                            TaskParticipant.task_id == task.id,
                            TaskParticipant.status.in_(["accepted", "joined"]),
                        )
                    )
                ).all()
            )
            approved_ids = set(
                (
                    await session.scalars(
                        select(TaskSubmission.user_id).where(
                            TaskSubmission.task_id == task.id,
                            TaskSubmission.status == "approved",
                        )
                    )
                ).all()
            )
            task.status = (
                TaskStatus.COMPLETED
                if member_ids and member_ids.issubset(approved_ids)
                else TaskStatus.IN_PROGRESS
            )
        return TaskReviewResult(
            submission=submission,
            admin_notice="Результат одобрен. Баллы и показатели обновлены один раз.",
            participant_notice=(
                f"Ваш результат по заданию одобрен.\n\n{task.title}\n\n"
                f"Начислено: {awarded_points} баллов"
            ),
            points_awarded=awarded_points,
        )

    if action == "revision":
        submission.status = "needs_revision"
        submission.admin_comment = comment
        submission.reviewed_by = actor.id
        task.status = TaskStatus.IN_PROGRESS
        return TaskReviewResult(
            submission=submission,
            admin_notice="Комментарий отправлен. Задание возвращено на доработку.",
            participant_notice=(
                f"Комментарий по заданию:\n\n{task.title}\n\n{comment}\n\nДоработайте результат "
                "и отправьте его повторно через Личный кабинет → Мои задачи."
            ),
            points_awarded=0,
        )

    submission.status = "rejected"
    submission.admin_comment = comment
    submission.reviewed_by = actor.id
    return TaskReviewResult(
        submission=submission,
        admin_notice="Результат отклонён. Баллы не начислены.",
        participant_notice=(
            f"Результат по заданию не принят.\n\n{task.title}\n\nПричина: {comment}\n\n"
            "Баллы не начислены."
        ),
        points_awarded=0,
    )
