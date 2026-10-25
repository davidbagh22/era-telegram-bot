from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PointTransaction, PortfolioItem, Task, TaskParticipant, TaskSubmission, User
from app.services.activity_scoring_service import score_task_completion
from app.services.audit_service import audit
from app.utils.constants import TaskStatus

TASK_REVIEW_ACTIONS = ("approve", "revision", "reject")


@dataclass(frozen=True)
class TaskReviewResult:
    submission: TaskSubmission
    admin_notice: str
    participant_notice: str | None
    points_awarded: int
    changed: bool = True


async def can_review_task(session: AsyncSession, actor: User | None, settings, task: Task) -> bool:
    if not (getattr(task, "reward_json", None) or {}).get("media_task"):
        return True
    if actor is None or settings is None:
        return False
    from app.services.media_service import can_manage_media
    current = await session.scalar(select(User).where(User.id == actor.id).execution_options(populate_existing=True))
    return current is not None and await can_manage_media(session, current, settings)


async def list_pending_submissions(session: AsyncSession, *, reviewer: User | None = None, settings=None) -> list[TaskSubmission]:
    query = select(TaskSubmission).join(Task, Task.id == TaskSubmission.task_id).where(
        TaskSubmission.status == "pending")
    if reviewer is not None:
        from app.services.media_service import can_manage_media
        current = await session.scalar(select(User).where(User.id == reviewer.id)
            .execution_options(populate_existing=True))
        media_allowed = settings is not None and current is not None and await can_manage_media(session, current, settings)
        if not media_allowed:
            # Apply visibility in SQL before the page limit: a full page of
            # media work must not hide older ordinary submissions.
            query = query.where(func.coalesce(Task.reward_json["media_task"].as_boolean(), False).is_(False))
    return list((await session.scalars(query.order_by(
        TaskSubmission.created_at.desc(), TaskSubmission.id.desc()).limit(30))).all())


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


async def _complete_public_participation(
    session: AsyncSession, task: Task, participant: User
) -> None:
    if not (task.reward_json or {}).get("public_task"):
        return
    task.status = "published"
    membership = await session.scalar(
        select(TaskParticipant)
        .where(
            TaskParticipant.task_id == task.id,
            TaskParticipant.user_id == participant.id,
        )
        .with_for_update()
    )
    if membership is not None:
        membership.status = "completed"


async def decide_submission(
    session: AsyncSession,
    submission: TaskSubmission,
    task: Task,
    participant: User,
    *,
    action: str,
    comment: str,
    actor: User,
    settings=None,
) -> TaskReviewResult:
    if action not in TASK_REVIEW_ACTIONS:
        raise ValueError(f"unknown task review action: {action!r}")
    if action in ("revision", "reject") and not comment.strip():
        raise ValueError("comment_required")

    # Serialize approvals for the same task before consulting the points ledger.
    task = await session.scalar(select(Task).where(Task.id == task.id).with_for_update()
        .execution_options(populate_existing=True))
    submission = await session.scalar(select(TaskSubmission).where(TaskSubmission.id == submission.id)
        .with_for_update().execution_options(populate_existing=True))
    if not task or not submission or submission.task_id != task.id or submission.user_id != participant.id:
        raise ValueError('submission_context_mismatch')
    if not await can_review_task(session, actor, settings, task):
        raise ValueError("media_review_access_required")
    if submission.status != 'pending':
        return TaskReviewResult(submission=submission,
            admin_notice=('Этот результат уже одобрен. Повторно баллы не начисляются.'
                if action == 'approve' and submission.status == 'approved'
                else 'Результат уже рассмотрен. Откройте актуальную карточку; прежнее решение сохранено.'),
            participant_notice=None, points_awarded=0, changed=False)
    await audit(session, actor_id=actor.id, action=f'task.submission_{action}',
        entity_type='task_submission', entity_id=submission.id, old_value={'status': 'pending'},
        new_value={'status': {'approve': 'approved', 'revision': 'needs_revision', 'reject': 'rejected'}[action]})

    if action == "approve":
        submission.status = "approved"
        submission.reviewed_by = actor.id
        submission.admin_comment = comment.strip() or None
        await _complete_public_participation(session, task, participant)
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

        # Verified public missions become a portfolio entry automatically;
        # the unique task/user check keeps retries idempotent.
        reward = task.reward_json or {}
        if reward.get("public_task") or reward.get("portfolio_on_approval") or reward.get("media_task"):
            portfolio = await session.scalar(select(PortfolioItem).where(PortfolioItem.user_id == participant.id, PortfolioItem.related_task_id == task.id))
            if portfolio is None:
                session.add(PortfolioItem(user_id=participant.id, title=task.title, item_type="task", description=submission.text or task.description, file_id=submission.file_id, related_task_id=task.id, issued_by=actor.id, verified_by=actor.id, admin_comment=submission.admin_comment, status="verified"))

        if reward.get('public_task'):
            # A participant's result never closes enrollment for everyone else.
            task.status = 'published'
        elif task.task_type == "private":
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
        task.status = 'published' if (task.reward_json or {}).get('public_task') else TaskStatus.IN_PROGRESS
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
