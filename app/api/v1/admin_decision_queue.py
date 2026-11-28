from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.rate_limit import enforce_rate_limit
from app.api.v1.admin import require_dashboard_access
from app.database.models import AuditLog, LeadershipAttentionItem, Task, TaskSubmission, User
from app.services import leadership_report_service
from app.services.analytics_snapshot_service import task_attention_condition
from app.services.audit_service import audit
from app.utils.constants import AttentionItemStatus, TaskStatus

router = APIRouter(prefix="/admin/decision-queue", tags=["admin-decision-queue"])

_ACTIVE_DECISION_STATUSES = ("open", "in_progress", "deferred")

_DECISION_TYPE_LABELS: dict[str, str] = {
    "blocker": "Блокер по задаче",
    "leaders_task": "Задача требует решения",
    "overdue_tasks": "Просроченные задачи",
    "missed_report": "Нет еженедельного отчёта",
    "pulse_blocker": "Блокер из Пульса",
    "pulse_help": "Запрос помощи из Пульса",
}


class DecisionQueueTaskOut(BaseModel):
    id: int
    title: str
    status: str
    deadline: str | None
    assignee_name: str | None
    points: int
    reasons: list[str]
    pending_submissions_count: int
    can_delete: bool


class DecisionQueueItemOut(BaseModel):
    id: int
    type: str
    severity: str
    status: str
    text: str
    owner_name: str | None
    scope_type: str
    scope_id: int | None
    task_id: int | None
    created_at: str | None


class DecisionQueueOut(BaseModel):
    tasks: list[DecisionQueueTaskOut]
    decisions: list[DecisionQueueItemOut]
    total: int


class DeleteDecisionIn(BaseModel):
    reason: str = Field(default="", max_length=500)


class DecisionMutationOut(BaseModel):
    kind: Literal["task", "decision"]
    id: int
    status: str
    deleted: bool = False
    restored: bool = False
    reversible: bool = True


def _full_name(user: User | None) -> str | None:
    if not user:
        return None
    name = " ".join(part for part in (user.first_name, user.last_name) if part).strip()
    if name:
        return name
    if user.username:
        return f"@{user.username}"
    return f"Участник #{user.id}"


def _is_overdue(deadline: datetime | None, now: datetime) -> bool:
    if deadline is None:
        return False
    aware = deadline if deadline.tzinfo is not None else deadline.replace(tzinfo=timezone.utc)
    return aware < now


async def _enforce_write_limit(request: Request) -> None:
    await enforce_rate_limit(
        request,
        key_prefix="admin_decision_queue_write",
        limit=30,
        window_seconds=60,
    )


@router.get("", response_model=DecisionQueueOut)
async def read_decision_queue(
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> DecisionQueueOut:
    """Live admin decision queue: tasks requiring attention and open leadership
    attention items."""
    now = datetime.now(timezone.utc)
    tasks = list(
        (
            await session.scalars(
                select(Task)
                .where(task_attention_condition(now))
                .order_by(Task.deadline.asc().nullslast(), Task.id.desc())
                .limit(100)
            )
        ).all()
    )
    decisions = list(
        (
            await session.scalars(
                select(LeadershipAttentionItem)
                .where(LeadershipAttentionItem.status.in_(_ACTIVE_DECISION_STATUSES))
                .order_by(LeadershipAttentionItem.created_at.desc(), LeadershipAttentionItem.id.desc())
                .limit(100)
            )
        ).all()
    )

    task_ids = [task.id for task in tasks]
    pending_counts: dict[int, int] = {}
    blocker_task_ids: set[int] = set()
    if task_ids:
        sub_rows = (
            await session.execute(
                select(TaskSubmission.task_id, func.count(TaskSubmission.id))
                .where(
                    TaskSubmission.task_id.in_(task_ids),
                    TaskSubmission.status == "pending",
                )
                .group_by(TaskSubmission.task_id)
            )
        ).all()
        pending_counts = {int(tid): int(cnt) for tid, cnt in sub_rows}
        blocker_task_ids = set(
            (
                await session.scalars(
                    select(LeadershipAttentionItem.scope_id).where(
                        LeadershipAttentionItem.scope_type == "task",
                        LeadershipAttentionItem.scope_id.in_(task_ids),
                        LeadershipAttentionItem.status.in_(("open", "in_progress")),
                    )
                )
            ).all()
        )

    user_ids = {
        uid
        for uid in (
            [task.assignee_id for task in tasks]
            + [item.owner_id for item in decisions]
        )
        if uid is not None
    }
    users_by_id: dict[int, User] = {}
    if user_ids:
        users = (await session.scalars(select(User).where(User.id.in_(user_ids)))).all()
        users_by_id = {u.id: u for u in users}

    task_items: list[DecisionQueueTaskOut] = []
    for task in tasks:
        pending_count = pending_counts.get(task.id, 0)
        reasons: list[str] = []
        if str(task.status) == TaskStatus.OVERDUE or _is_overdue(task.deadline, now):
            reasons.append("overdue")
        if str(task.status) == TaskStatus.REVIEW:
            reasons.append("review")
        if pending_count > 0:
            reasons.append("pending_submission")
        if task.id in blocker_task_ids:
            reasons.append("blocker")
        task_items.append(
            DecisionQueueTaskOut(
                id=task.id,
                title=task.title,
                status=str(task.status),
                deadline=task.deadline.isoformat() if task.deadline else None,
                assignee_name=_full_name(users_by_id.get(task.assignee_id)) if task.assignee_id else None,
                points=int(task.points or 0),
                reasons=reasons,
                pending_submissions_count=pending_count,
                can_delete=pending_count == 0,
            )
        )

    decision_items: list[DecisionQueueItemOut] = []
    for item in decisions:
        text = (item.resolution or "").strip() or _DECISION_TYPE_LABELS.get(item.type, "Запрос требует решения")
        decision_items.append(
            DecisionQueueItemOut(
                id=item.id,
                type=item.type,
                severity=str(item.severity),
                status=str(item.status),
                text=text,
                owner_name=_full_name(users_by_id.get(item.owner_id)) if item.owner_id else None,
                scope_type=item.scope_type,
                scope_id=item.scope_id,
                task_id=item.scope_id if item.scope_type == "task" else None,
                created_at=item.created_at.isoformat() if item.created_at else None,
            )
        )

    return DecisionQueueOut(
        tasks=task_items,
        decisions=decision_items,
        total=len(task_items) + len(decision_items),
    )


@router.delete(
    "/decisions/{item_id}",
    response_model=DecisionMutationOut,
    dependencies=[Depends(_enforce_write_limit)],
)
async def delete_decision_item(
    item_id: int,
    payload: DeleteDecisionIn | None = Body(default=None),
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> DecisionMutationOut:
    item = await session.get(LeadershipAttentionItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="decision_not_found")
    if str(item.status) == AttentionItemStatus.DISMISSED:
        raise HTTPException(status_code=409, detail="decision_already_deleted")
    await leadership_report_service.dismiss_attention_item(
        session,
        item,
        actor_id=admin.id,
        reason=payload.reason if payload else None,
    )
    await session.flush()
    return DecisionMutationOut(
        kind="decision",
        id=item.id,
        status=str(item.status),
        deleted=True,
        reversible=True,
    )


@router.post(
    "/decisions/{item_id}/restore",
    response_model=DecisionMutationOut,
    dependencies=[Depends(_enforce_write_limit)],
)
async def restore_decision_item(
    item_id: int,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> DecisionMutationOut:
    item = await session.get(LeadershipAttentionItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="decision_not_found")
    if str(item.status) != AttentionItemStatus.DISMISSED:
        raise HTTPException(status_code=409, detail="decision_not_deleted")
    await leadership_report_service.restore_attention_item(session, item, actor_id=admin.id)
    await session.flush()
    return DecisionMutationOut(
        kind="decision",
        id=item.id,
        status=str(item.status),
        restored=True,
        reversible=True,
    )


@router.delete(
    "/tasks/{task_id}",
    response_model=DecisionMutationOut,
    dependencies=[Depends(_enforce_write_limit)],
)
async def delete_decision_task(
    task_id: int,
    payload: DeleteDecisionIn | None = Body(default=None),
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> DecisionMutationOut:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    if str(task.status) == TaskStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="task_already_cancelled")
    if str(task.status) == TaskStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="task_already_completed")

    pending_submissions = int(
        await session.scalar(
            select(func.count(TaskSubmission.id)).where(
                TaskSubmission.task_id == task.id,
                TaskSubmission.status == "pending",
            )
        )
        or 0
    )
    if pending_submissions > 0:
        raise HTTPException(status_code=409, detail="pending_submission_exists")

    clean_reason = (payload.reason if payload else "").strip()[:500] or None
    old_status = str(task.status)
    task.status = TaskStatus.CANCELLED

    linked_items = list(
        (
            await session.scalars(
                select(LeadershipAttentionItem).where(
                    LeadershipAttentionItem.scope_type == "task",
                    LeadershipAttentionItem.scope_id == task.id,
                    LeadershipAttentionItem.status.in_(_ACTIVE_DECISION_STATUSES),
                )
            )
        ).all()
    )
    closed_attention_ids: list[int] = []
    for attention in linked_items:
        await leadership_report_service.dismiss_attention_item(
            session,
            attention,
            actor_id=admin.id,
            reason=clean_reason or "Задача удалена из очереди решений",
        )
        closed_attention_ids.append(attention.id)

    await audit(
        session,
        actor_id=admin.id,
        action="admin.decision_task_deleted",
        entity_type="task",
        entity_id=task.id,
        old_value={
            "status": old_status,
            "title": task.title,
            "closed_attention_ids": closed_attention_ids,
        },
        new_value={"status": str(task.status), "reason": clean_reason},
    )
    await session.flush()
    return DecisionMutationOut(
        kind="task",
        id=task.id,
        status=str(task.status),
        deleted=True,
        reversible=True,
    )


@router.post(
    "/tasks/{task_id}/restore",
    response_model=DecisionMutationOut,
    dependencies=[Depends(_enforce_write_limit)],
)
async def restore_decision_task(
    task_id: int,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> DecisionMutationOut:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    if str(task.status) != TaskStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="task_not_deleted")

    last_delete = await session.scalar(
        select(AuditLog)
        .where(
            AuditLog.entity_type == "task",
            AuditLog.entity_id == task.id,
            AuditLog.action == "admin.decision_task_deleted",
        )
        .order_by(AuditLog.id.desc())
        .limit(1)
    )
    old_data = last_delete.old_value if last_delete and isinstance(last_delete.old_value, dict) else {}
    restored_status = str(old_data.get("status") or TaskStatus.PUBLISHED)
    if restored_status in (TaskStatus.CANCELLED, TaskStatus.COMPLETED):
        restored_status = TaskStatus.PUBLISHED
    task.status = restored_status

    restored_attention_ids: list[int] = []
    raw_attention_ids = old_data.get("closed_attention_ids") or []
    if isinstance(raw_attention_ids, list) and raw_attention_ids:
        linked = (
            await session.scalars(
                select(LeadershipAttentionItem).where(
                    LeadershipAttentionItem.id.in_(raw_attention_ids),
                    LeadershipAttentionItem.status == AttentionItemStatus.DISMISSED,
                )
            )
        ).all()
        for attention in linked:
            await leadership_report_service.restore_attention_item(
                session, attention, actor_id=admin.id
            )
            restored_attention_ids.append(attention.id)

    await audit(
        session,
        actor_id=admin.id,
        action="admin.decision_task_restored",
        entity_type="task",
        entity_id=task.id,
        old_value={"status": TaskStatus.CANCELLED},
        new_value={
            "status": str(task.status),
            "restored_attention_ids": restored_attention_ids,
        },
    )
    await session.flush()
    return DecisionMutationOut(
        kind="task",
        id=task.id,
        status=str(task.status),
        restored=True,
        reversible=True,
    )
