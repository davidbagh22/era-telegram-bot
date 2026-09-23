from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.api.rate_limit import enforce_rate_limit
from app.config import Settings
from app.database.models import Office, User, UserOffice
from app.services import office_management_service
from app.services.authorization_service import can_manage_people
from app.services.audit_service import audit

router = APIRouter(prefix="/admin", tags=["admin-recruitment"])


async def require_people_manager(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_people(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="people_manage_required")
    return user


async def rate_limit_action(request: Request) -> None:
    await enforce_rate_limit(request, key_prefix="admin_recruitment_assignment", limit=30, window_seconds=60)


@router.post("/offices/assignments/{assignment_id}/remove")
async def remove_office_assignment_reconciled(
    assignment_id: int,
    manager: User = Depends(require_people_manager),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(rate_limit_action),
) -> dict[str, bool]:
    assignment = await session.scalar(
        select(UserOffice).where(UserOffice.id == assignment_id).with_for_update()
    )
    if assignment is None or not assignment.is_active:
        raise HTTPException(status_code=404, detail="assignment_not_found")
    office = await session.scalar(
        select(Office).where(Office.id == assignment.office_id).with_for_update()
    )
    office_management_service.remove_assignment(
        assignment,
        ended_by_id=manager.id,
        reason="manual_admin_removal",
    )
    if office is not None:
        await office_management_service.reconcile_office_vacancy(session, office)
    await audit(
        session,
        actor_id=manager.id,
        action="appointment.ended",
        entity_type="user_office",
        entity_id=assignment.id,
        old_value={"is_active": True},
        new_value={"is_active": False, "reason": "manual_admin_removal"},
    )
    return {"ok": True}
