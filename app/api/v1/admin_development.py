from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.database.development_models import (
    AdminVisibilitySetting,
    GoalReview,
    MonthlyCheckin,
    UserVectorProfile,
)
from app.database.models import User
from app.services import development_service as dev

router = APIRouter(prefix="/admin/development", tags=["admin-development"])


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="development_admin_access_required")


@router.get("/participants/{user_id}")
async def participant_development(
    user_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_admin(user)
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")

    visibility = await session.get(AdminVisibilitySetting, user_id)
    if visibility is None or not visibility.summary_visible:
        await dev.audit(
            session,
            user.id,
            "development.admin.profile.denied",
            target_user_id=user_id,
        )
        raise HTTPException(status_code=403, detail="development_summary_not_shared")

    profile = await session.get(UserVectorProfile, user_id)
    history = (
        await session.scalars(
            select(MonthlyCheckin)
            .where(
                MonthlyCheckin.user_id == user_id,
                MonthlyCheckin.status == "completed",
            )
            .order_by(desc(MonthlyCheckin.month))
            .limit(12)
        )
    ).all()
    goal = await dev.latest_goal(session, user_id)
    review = (
        await session.scalar(select(GoalReview).where(GoalReview.goal_id == goal.id))
        if goal
        else None
    )

    await dev.audit(
        session,
        user.id,
        "development.admin.profile.read",
        target_user_id=user_id,
        metadata={"shared_summary": True},
    )

    return {
        "user": {
            "id": target.id,
            "first_name": target.first_name,
            "last_name": target.last_name,
        },
        "last_checkin_at": profile.last_checkin_at if profile else None,
        "state": profile.state_json if profile else {},
        "index": profile.current_index if profile else None,
        "baseline": profile.baseline_json if profile else {},
        "traits": profile.traits_json if profile else {},
        "needs": profile.needs_json if profile else {},
        "interests": (
            profile.interests_json if profile and visibility.interests_visible else None
        ),
        "strengths": (
            profile.strengths_json if profile and visibility.interests_visible else None
        ),
        "environment": (
            profile.environment_json if profile and visibility.interests_visible else None
        ),
        "current_focus": (
            {
                "title": goal.title,
                "experiment": goal.experiment,
                "status": goal.status,
                "review_result": review.result if review else None,
            }
            if goal and visibility.goals_visible
            else None
        ),
        "history": [
            {
                "month": row.month,
                "index": row.index_value,
                "state": row.state_json,
                "delta": row.delta_json,
            }
            for row in history
        ],
        "notice": (
            "Эти данные помогают понимать потребности и развитие. Они не оценивают "
            "пригодность, надёжность или ценность человека и не могут использоваться "
            "для автоматического отбора."
        ),
        "never_exposed_here": [
            "personal_notes",
            "raw_sensitive_answers",
            "hidden_insights",
            "assessment_answer_rows",
        ],
    }


@router.get("/analytics")
async def development_analytics(
    period_days: int = 30,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_admin(user)
    result = await dev.community_analytics(session, period_days=period_days)
    await dev.audit(
        session,
        user.id,
        "development.admin.analytics.read",
        metadata={
            "period_days": max(1, min(period_days, 365)),
            "suppressed": result["suppressed"],
        },
    )
    return result
