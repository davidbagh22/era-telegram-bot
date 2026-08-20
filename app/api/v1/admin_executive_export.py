from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import User
from app.services.admin_analytics_service import build_analytics_payload
from app.services.admin_dashboard_service import has_dashboard_access
from app.services.era_efficiency_service import build_efficiency_snapshot
from app.services.executive_excel_service import build_executive_workbook, resolve_report_period
from app.services.organization_health_extended_service import build_extended_organization_health

router = APIRouter(prefix="/admin/analytics", tags=["admin-executive-export"])

ReportPeriod = Literal["30d", "3m", "6m", "1y", "custom"]


async def require_admin(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not has_dashboard_access(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="admin_access_required")
    return user


@router.get("/executive-report.xlsx")
async def export_executive_report(
    period: ReportPeriod = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """MASTER §54 executive workbook with period selection and privacy guardrails."""
    try:
        start, end, label = resolve_report_period(
            period,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    analytics = await build_analytics_payload(session)
    efficiency = await build_efficiency_snapshot(session)
    health = await build_extended_organization_health(session)
    content = await build_executive_workbook(
        session,
        analytics=analytics,
        health=health,
        efficiency=efficiency,
        start_date=start,
        end_date=end,
        period_label=label,
    )
    suffix = f"{start:%Y%m%d}-{end:%Y%m%d}"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="ERA_executive_{suffix}.xlsx"'},
    )
