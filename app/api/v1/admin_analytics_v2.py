from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.deps import get_bot, get_session, get_settings
from app.api.v1.admin_executive_export import require_admin
from app.services.admin_analytics_v2_service import build_v2_snapshot
from app.services.telegram_analytics_service import refresh_sources, report_window

router = APIRouter(prefix='/admin/analytics/v2', tags=['admin-analytics-v2'])


@router.get('')
async def overview(days: Literal[7, 30, 90] = Query(30), start_date: date | None = None,
                   end_date: date | None = None, _admin=Depends(require_admin),
                   session=Depends(get_session), settings=Depends(get_settings)):
    try:
        start, end = report_window(days=days, start_date=start_date, end_date=end_date, timezone_name=settings.timezone)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return await build_v2_snapshot(session, settings, start=start, end=end)


@router.post('/sources/check')
async def check_sources(_admin=Depends(require_admin), session=Depends(get_session),
                        settings=Depends(get_settings), bot=Depends(get_bot)):
    await refresh_sources(session, bot, settings)
    await session.commit()
    return {'ok': True}


@router.get('/reports')
async def reports(_admin=Depends(require_admin), session=Depends(get_session)):
    from sqlalchemy import select
    from app.database.models import AuditLog
    rows = (await session.scalars(select(AuditLog).where(
        AuditLog.actor_id == _admin.id, AuditLog.action == 'analytics.report_generated'
    ).order_by(AuditLog.created_at.desc()).limit(30))).all()
    return {'items': [{'generated_at': row.created_at.isoformat(), **(row.new_value or {})} for row in rows]}
