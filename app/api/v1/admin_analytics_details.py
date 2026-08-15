from __future__ import annotations

import csv
from enum import Enum
from io import BytesIO, StringIO
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import User
from app.services.admin_analytics_service import build_analytics_payload
from app.services.admin_dashboard_service import has_dashboard_access
from app.services.era_efficiency_service import build_efficiency_snapshot
from app.services.excel_service import build_analytics_workbook

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics-details"])
AnalyticsDetailSection = Literal["users", "events", "projects", "contacts", "goals"]


async def require_dashboard_access(user: User = Depends(get_current_user), settings: Settings = Depends(get_settings)) -> User:
    if not has_dashboard_access(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="admin_access_required")
    return user


class AnalyticsDetailItemOut(BaseModel):
    id: int
    title: str
    subtitle: str | None = None
    status: str | None = None


class AnalyticsDetailsOut(BaseModel):
    section: AnalyticsDetailSection
    total: int
    items: list[AnalyticsDetailItemOut]


class EfficiencyMetricOut(BaseModel):
    key: str
    label: str
    value: float
    display: str
    score: int | None
    note: str


class EfficiencyRecommendationOut(BaseModel):
    priority: str
    title: str
    reason: str
    action: str


class EfficiencyOut(BaseModel):
    score: int
    label: str
    period_label: str
    metrics: list[EfficiencyMetricOut]
    recommendations: list[EfficiencyRecommendationOut]
    top_interest: str | None
    top_interest_count: int
    data_note: str


def _text(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        value = value.value
    rendered = str(value).strip()
    return rendered or None


def _detail_items(section: AnalyticsDetailSection, data) -> list[AnalyticsDetailItemOut]:
    if section == "users":
        return [AnalyticsDetailItemOut(
            id=user.id,
            title=" ".join(part for part in [user.first_name, user.last_name] if part).strip() or f"Участник #{user.id}",
            subtitle=" · ".join(part for part in [_text(user.role), f"@{user.username}" if user.username else None] if part) or None,
            status=_text(user.application_status),
        ) for user in data.users]
    if section == "events":
        return [AnalyticsDetailItemOut(
            id=event.id, title=event.title,
            subtitle=" · ".join(part for part in [event.event_date.isoformat() if event.event_date else None, event.event_time.strftime("%H:%M") if event.event_time else None] if part) or None,
            status=_text(event.status),
        ) for event in data.events]
    if section == "projects":
        return [AnalyticsDetailItemOut(
            id=project.id, title=project.title,
            subtitle=project.created_at.date().isoformat() if project.created_at else None,
            status=_text(project.status),
        ) for project in data.projects]
    if section == "contacts":
        return [AnalyticsDetailItemOut(id=contact.id, title=contact.organization_name, status="active") for contact in data.contacts]
    return [AnalyticsDetailItemOut(
        id=goal.id, title=goal.title,
        subtitle=f"{goal.scope_name} · {goal.current_value}/{goal.target_value}", status=goal.status,
    ) for goal in data.goals]


def _with_efficiency_sheet(content: bytes, snapshot) -> bytes:
    from openpyxl import load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = load_workbook(BytesIO(content))
    if "Эффективность" in wb.sheetnames:
        del wb["Эффективность"]
    ws = wb.create_sheet("Эффективность", 0)
    ws.sheet_view.showGridLines = False
    ws["A1"] = "ERA PULSE"
    ws["A1"].font = Font(size=18, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor="E32636")
    ws.merge_cells("A1:D1")
    ws["A2"] = f"{snapshot.score}/100 · {snapshot.label}"
    ws["A2"].font = Font(size=14, bold=True, color="151619")
    ws.merge_cells("A2:D2")
    ws["A3"] = snapshot.data_note
    ws.merge_cells("A3:D3")
    ws.append([])
    ws.append(["Показатель", "Значение", "Оценка / 100", "Что это значит"])
    for metric in snapshot.metrics:
        ws.append([metric.label, metric.display, metric.score if metric.score is not None else "—", metric.note])
    ws.append([])
    ws.append(["ЧТО СДЕЛАТЬ НА ЭТОЙ НЕДЕЛЕ", "Почему", "Что сделать", "Приоритет"])
    for item in snapshot.recommendations:
        ws.append([item.title, item.reason, item.action, item.priority])
    for cell in ws[5]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="151619")
    recommendation_header_row = 7 + len(snapshot.metrics)
    for cell in ws[recommendation_header_row]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="981B28")
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 42
    ws.column_dimensions["C"].width = 58
    ws.column_dimensions["D"].width = 24
    ws.freeze_panes = "A5"
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


def _detail_xlsx(section: AnalyticsDetailSection, items: list[AnalyticsDetailItemOut]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Данные"
    ws.sheet_view.showGridLines = False
    ws.append(["ID", "Название", "Детали", "Статус"])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="E32636")
    for item in items:
        ws.append([item.id, item.title, item.subtitle or "", item.status or ""])
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 38
    ws.column_dimensions["C"].width = 48
    ws.column_dimensions["D"].width = 24
    ws.freeze_panes = "A2"
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


@router.get("/weekly", response_model=EfficiencyOut)
async def read_weekly_efficiency(_admin: User = Depends(require_dashboard_access), session: AsyncSession = Depends(get_session)) -> EfficiencyOut:
    snapshot = await build_efficiency_snapshot(session)
    return EfficiencyOut(
        score=snapshot.score, label=snapshot.label, period_label=snapshot.period_label,
        metrics=[EfficiencyMetricOut(**item.__dict__) for item in snapshot.metrics],
        recommendations=[EfficiencyRecommendationOut(**item.__dict__) for item in snapshot.recommendations],
        top_interest=snapshot.top_interest, top_interest_count=snapshot.top_interest_count, data_note=snapshot.data_note,
    )


@router.get("/full-report.xlsx")
async def export_full_analytics_report(_admin: User = Depends(require_dashboard_access), session: AsyncSession = Depends(get_session)) -> Response:
    data = await build_analytics_payload(session)
    snapshot = await build_efficiency_snapshot(session)
    base = build_analytics_workbook(data.users, data.events, data.projects, data.totals, department_stats=data.department_stats, direction_stats=data.direction_stats, goals=data.goals, contacts=data.contacts)
    content = _with_efficiency_sheet(base, snapshot)
    return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": 'attachment; filename="ERA_full_report.xlsx"'})


@router.get("/details/{section}", response_model=AnalyticsDetailsOut)
async def read_analytics_details(section: AnalyticsDetailSection, _admin: User = Depends(require_dashboard_access), session: AsyncSession = Depends(get_session)) -> AnalyticsDetailsOut:
    items = _detail_items(section, await build_analytics_payload(session))
    return AnalyticsDetailsOut(section=section, total=len(items), items=items)


@router.get("/details/{section}/export.csv")
async def export_analytics_details_csv(section: AnalyticsDetailSection, _admin: User = Depends(require_dashboard_access), session: AsyncSession = Depends(get_session)) -> Response:
    items = _detail_items(section, await build_analytics_payload(session))
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["ID", "Название", "Детали", "Статус"])
    for item in items:
        writer.writerow([item.id, item.title, item.subtitle or "", item.status or ""])
    payload = "\ufeff" + buffer.getvalue()
    return Response(content=payload.encode("utf-8"), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="ERA_{section}.csv"'})


@router.get("/details/{section}/export.xlsx")
async def export_analytics_details_xlsx(section: AnalyticsDetailSection, _admin: User = Depends(require_dashboard_access), session: AsyncSession = Depends(get_session)) -> Response:
    items = _detail_items(section, await build_analytics_payload(session))
    return Response(
        content=_detail_xlsx(section, items),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="ERA_{section}.xlsx"'},
    )
