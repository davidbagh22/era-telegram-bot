"""Self-service data export and account-deletion requests.

Closes docs/FINAL_PRODUCTION_ACCEPTANCE.md items #118 (deletion process)
and #119 (export process) — the two items docs/DATA_INVENTORY.md section 4
had honestly disclosed as "not implemented" going into that audit.

Deliberate design choice, consistent with the rest of this app's data
model: deletion is request → admin-reviewed anonymization, not an
instant self-service hard-delete. See DataDeletionRequest's own
docstring in app/database/models.py for why (PointTransaction is a
retained financial-record-like ledger; a real hard-delete would also
break referential integrity for anything this user authored/reviewed).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    ConsentLog,
    DataDeletionRequest,
    EventRegistration,
    PointTransaction,
    PortfolioItem,
    User,
)
from app.services.audit_service import audit

PENDING = "pending"
FULFILLED = "fulfilled"
REJECTED = "rejected"

# Fields cleared on fulfillment — everything DATA_INVENTORY.md §1 marks as
# "Персональные" or "Чувствительные" and that isn't itself needed to keep
# other rows (points, project authorship, audit trail) referentially
# meaningful. role/participation_status/is_archived and the relationships
# to departments/directions/points/projects are deliberately left alone —
# anonymizing, not deleting the row, is the whole point.
_ANONYMIZED_STRING_FIELDS = (
    "username",
    "phone",
    "email",
    "city",
    "education_work",
    "occupation",
    "experience",
    "motivation",
    "available_time",
    "desired_path",
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _row_to_dict(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: _json_safe(getattr(row, field)) for field in fields}


async def export_user_data(session: AsyncSession, user: User) -> dict[str, Any]:
    """Everything this app actually stores about the caller's own account,
    as a JSON-serializable dict — the Mini App's `/profile/export` returns
    this directly as a downloadable file. Deliberately scoped to what
    docs/DATA_INVENTORY.md §1-2 lists, not a raw ORM dump of every table
    this user_id happens to appear in as a foreign key (e.g. as someone
    else's `approved_by`/`reviewed_by`) — that's this app's *decisions
    about* other people's data, not this user's *own* data."""
    profile_fields = (
        "id", "telegram_id", "username", "first_name", "last_name",
        "birth_date", "age", "phone", "email", "city", "education_work",
        "occupation", "skills", "experience", "motivation",
        "available_time", "desired_path", "role", "participation_status",
        "application_status", "is_blocked", "is_archived",
        "personal_data_consent", "created_at",
    )
    profile = _row_to_dict(user, profile_fields)
    profile["departments"] = [link.department.name for link in user.departments]
    profile["directions"] = [link.direction.name for link in user.directions]

    consent_rows = (
        await session.scalars(
            select(ConsentLog).where(ConsentLog.user_id == user.id).order_by(ConsentLog.created_at)
        )
    ).all()
    points_rows = (
        await session.scalars(
            select(PointTransaction)
            .where(PointTransaction.user_id == user.id)
            .order_by(PointTransaction.created_at)
        )
    ).all()
    registration_rows = (
        await session.scalars(
            select(EventRegistration)
            .where(EventRegistration.user_id == user.id)
            .order_by(EventRegistration.created_at)
        )
    ).all()
    portfolio_rows = (
        await session.scalars(
            select(PortfolioItem)
            .where(PortfolioItem.user_id == user.id)
            .order_by(PortfolioItem.created_at)
        )
    ).all()

    return {
        "exported_at": datetime.now().astimezone().isoformat(),
        "profile": profile,
        "consent_log": [
            _row_to_dict(row, ("consent_type", "policy_version", "granted", "source", "created_at"))
            for row in consent_rows
        ],
        "points": [
            _row_to_dict(row, ("points", "reason", "source_type", "created_at"))
            for row in points_rows
        ],
        "event_registrations": [
            _row_to_dict(row, ("event_id", "status", "created_at"))
            for row in registration_rows
        ],
        "portfolio_items": [
            _row_to_dict(row, ("title", "item_type", "description", "status", "created_at"))
            for row in portfolio_rows
        ],
    }


async def request_deletion(session: AsyncSession, user: User, note: str | None) -> DataDeletionRequest:
    existing = await session.scalar(
        select(DataDeletionRequest).where(
            DataDeletionRequest.user_id == user.id,
            DataDeletionRequest.status == PENDING,
        )
    )
    if existing is not None:
        return existing
    request = DataDeletionRequest(user_id=user.id, status=PENDING, note=note)
    session.add(request)
    await session.flush()
    await audit(
        session,
        actor_id=user.id,
        action="user.deletion_requested",
        entity_type="user",
        entity_id=user.id,
        new_value={"request_id": request.id, "note": note},
    )
    return request


async def list_deletion_requests(session: AsyncSession, *, status: str = PENDING) -> list[DataDeletionRequest]:
    return list(
        (
            await session.scalars(
                select(DataDeletionRequest)
                .where(DataDeletionRequest.status == status)
                .order_by(DataDeletionRequest.created_at)
            )
        ).all()
    )


@dataclass(frozen=True)
class FulfillResult:
    request_id: int
    status: str


async def fulfill_deletion_request(
    session: AsyncSession,
    request: DataDeletionRequest,
    *,
    admin: User,
    approve: bool,
) -> FulfillResult:
    if request.status != PENDING:
        return FulfillResult(request_id=request.id, status=request.status)

    target = await session.get(User, request.user_id)
    if target is None:
        request.status = REJECTED
        request.fulfilled_at = datetime.now().astimezone()
        request.fulfilled_by = admin.id
        return FulfillResult(request_id=request.id, status=REJECTED)

    if approve:
        for field in _ANONYMIZED_STRING_FIELDS:
            setattr(target, field, None)
        target.first_name = "Удалённый пользователь"
        target.last_name = None
        target.birth_date = None
        target.age = None
        target.skills = []
        target.is_archived = True
        target.archived_at = datetime.now().astimezone()
        target.archived_by = admin.id
        request.status = FULFILLED
        action = "user.deletion_fulfilled"
    else:
        request.status = REJECTED
        action = "user.deletion_rejected"

    request.fulfilled_at = datetime.now().astimezone()
    request.fulfilled_by = admin.id
    await audit(
        session,
        actor_id=admin.id,
        action=action,
        entity_type="user",
        entity_id=target.id,
        old_value={"request_id": request.id},
    )
    return FulfillResult(request_id=request.id, status=request.status)
