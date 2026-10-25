from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.database.development_models import (
    AdminVisibilitySetting,
    GoalReview,
    MonthlyCheckin,
    UserVectorProfile,
)
from app.database.models import User
from app.services import development_analytics as dev_analytics
from app.services import development_service as dev
from app.services.authorization_service import is_full_admin
from app.services.excel_quality_service import finalize_business_workbook
from app.services.excel_report_service import build_development_workbook

router = APIRouter(prefix="/admin/development", tags=["admin-development"])


def _has_permission(user: User, permission: str, settings: Settings) -> bool:
    if is_full_admin(user, settings, user.telegram_id):
        return True
    return any(
        grant.is_active
        and grant.permission == permission
        and grant.scope_type == "global"
        for grant in (user.permission_grants or [])
    )


def _require_permission(user: User, permission: str, settings: Settings) -> None:
    if not _has_permission(user, permission, settings):
        raise HTTPException(status_code=403, detail=f"permission_required:{permission}")


@router.get("/participants/{user_id}")
async def participant_development(
    user_id: int,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_permission(user, "development.admin.individual.read", settings)
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
            metadata={"reason": "user_visibility"},
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
        metadata={"shared_summary": True, "permission": "development.admin.individual.read"},
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
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_permission(user, "development.admin.analytics.read", settings)
    result = await dev_analytics.community_analytics(session, period_days=period_days)
    await dev.audit(
        session,
        user.id,
        "development.admin.analytics.read",
        metadata={
            "period_days": max(1, min(period_days, 365)),
            "suppressed": result["suppressed"],
            "sample_size": result["sample_size"],
            "permission": "development.admin.analytics.read",
        },
    )
    return result


async def _audit_export(
    session: AsyncSession,
    user: User,
    period_days: int,
    result: dict[str, Any],
    format_name: str,
) -> None:
    await dev.audit(
        session,
        user.id,
        "development.admin.analytics.export",
        metadata={
            "period_days": max(1, min(period_days, 365)),
            "suppressed": result["suppressed"],
            "sample_size": result["sample_size"],
            "permission": "development.admin.export",
            "format": format_name,
        },
    )


@router.get("/analytics/export.xlsx")
async def export_development_analytics_xlsx(
    period_days: int = 30,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> Response:
    _require_permission(user, "development.admin.export", settings)
    result = await dev_analytics.community_analytics(session, period_days=period_days)
    content = finalize_business_workbook(build_development_workbook(result))
    await _audit_export(session, user, period_days, result, "xlsx")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ERA_My_Vector.xlsx"},
    )


# Compatibility for older clients; the current Mini App uses the polished XLSX.
@router.get("/analytics/export")
async def export_development_analytics(
    period_days: int = 30,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> Response:
    _require_permission(user, "development.admin.export", settings)
    result = await dev_analytics.community_analytics(session, period_days=period_days)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["section", "indicator", "value", "count", "coverage_percent"])
    writer.writerow([
        "coverage",
        "checkins",
        result["sample_size"],
        result["eligible_profiles"],
        result["coverage_percent"],
    ])
    if not result["suppressed"]:
        for code in dev.STATE_DIMENSIONS:
            writer.writerow([
                "state",
                dev.STATE_LABELS[code],
                result["state"].get(code, ""),
                result["sample_size"],
                result["coverage_percent"],
            ])
        for item in result.get("development_wants", []):
            writer.writerow(["development_wants", item["key"], item["percent"], item["count"], result["coverage_percent"]])
        for item in result.get("interests", []):
            writer.writerow(["interests", item["key"], item["percent"], item["count"], result["coverage_percent"]])
    await _audit_export(session, user, period_days, result, "csv")
    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=era_my_vector_analytics.csv"},
    )
