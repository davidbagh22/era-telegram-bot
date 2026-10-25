from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from typing import Any
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analytics_snapshot_service import count_new_members, verified_users_between
from app.database.models import (
    EventRegistration,
    LeadershipAttentionItem,
    PortfolioItem,
    ProjectMember,
    ProjectMilestone,
    RewardRedemption,
    Task,
    TaskSubmission,
    User,
    AuditLog,
)
from app.database.participation_models import ParticipationLifecycle
from app.utils.constants import ApplicationStatus


SHEET_NAMES = [
    "01 · Сводка",
    "02 · Люди",
    "03 · Рост",
    "04 · Департаменты",
    "05 · Направления",
    "06 · Мой вектор",
    "07 · События",
    "08 · Проекты",
    "09 · Задания",
    "10 · Возможности и документы",
    "11 · Портфолио и признание",
    "12 · Решения",
    "13 · Методика",
]

ERA_DARK = "111216"
ERA_RED = "E32636"
ERA_CREAM = "F3E8D5"
ERA_LIGHT = "F7F4EF"


def resolve_report_period(
    period: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    today: date | None = None,
) -> tuple[date, date, str]:
    end = end_date or today or datetime.now(timezone.utc).date()
    if period == "custom":
        if start_date is None or end_date is None or start_date > end_date:
            raise ValueError("invalid_custom_period")
        return start_date, end_date, f"{start_date:%d.%m.%Y}–{end_date:%d.%m.%Y}"
    days = {"30d": 30, "3m": 90, "6m": 180, "1y": 365}.get(period)
    if days is None:
        raise ValueError("invalid_report_period")
    start = end - timedelta(days=days - 1)
    return start, end, {"30d": "30 дней", "3m": "3 месяца", "6m": "6 месяцев", "1y": "1 год"}[period]


def _date_of(value: Any, timezone_name: str = 'Asia/Yerevan') -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return aware.astimezone(ZoneInfo(timezone_name)).date()
    if isinstance(value, date):
        return value
    return None


def _in_period(value: Any, start: date, end: date, timezone_name: str = 'Asia/Yerevan') -> bool:
    day = _date_of(value, timezone_name)
    return day is not None and start <= day <= end


def _enum(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "—")


def _name(user: User | None) -> str:
    if user is None:
        return "—"
    return " ".join(part for part in (user.first_name, user.last_name) if part).strip() or "Участник"


def _telegram(user: User | None) -> str:
    if user is None:
        return "—"
    return f"@{user.username}" if user.username else "—"


def _append_table(ws, headers: list[str], rows: list[list[Any]]) -> None:
    ws.append(headers)
    for cell in ws[ws.max_row]:
        cell.fill = PatternFill("solid", fgColor=ERA_DARK)
        cell.font = Font(name="Aptos", bold=True, color=ERA_CREAM)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    if not rows:
        rows = [["Данных за выбранный период нет"] + [""] * (len(headers) - 1)]
    for row in rows:
        ws.append(row)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(ws.max_column)}{ws.max_row}"
    for col in range(1, ws.max_column + 1):
        values = [str(ws.cell(row, col).value or "") for row in range(1, min(ws.max_row, 100) + 1)]
        ws.column_dimensions[get_column_letter(col)].width = min(max(max(map(len, values), default=0) + 2, 11), 42)


def _summary_sheet(ws, *, period_label: str, rows: list[list[Any]]) -> None:
    ws.sheet_view.showGridLines = False
    ws.merge_cells("A1:D1")
    ws["A1"] = "ERA PLATFORM · EXECUTIVE REPORT"
    ws["A1"].fill = PatternFill("solid", fgColor=ERA_DARK)
    ws["A1"].font = Font(name="Aptos Display", size=18, bold=True, color=ERA_CREAM)
    ws["A2"] = f"Период: {period_label}"
    ws["A2"].font = Font(name="Aptos", italic=True, color="666666")
    ws.append([])
    ws.append(["Показатель", "Значение", "Что означает", "Источник"])
    for cell in ws[4]:
        cell.fill = PatternFill("solid", fgColor=ERA_RED)
        cell.font = Font(name="Aptos", bold=True, color="FFFFFF")
    for row in rows:
        ws.append(row)
    ws.freeze_panes = "A5"
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 48
    ws.column_dimensions["D"].width = 32


async def build_executive_workbook(
    session: AsyncSession,
    *,
    analytics,
    health,
    efficiency,
    start_date: date,
    end_date: date,
    period_label: str,
    timezone_name: str = "Asia/Yerevan",
) -> bytes:
    """Build the single executive workbook defined by MASTER section 54.

    It deliberately contains no database/Telegram technical IDs and no raw My
    Vector answers. Vector data enters only through the already cohort-suppressed
    organization-health aggregate supplied by ``build_extended_organization_health``.
    """

    users = list(analytics.users)
    approved = [u for u in users if u.application_status == ApplicationStatus.APPROVED]

    lifecycles = list((await session.scalars(select(ParticipationLifecycle))).all())
    lifecycle_by_user = {item.user_id: item for item in lifecycles}
    current_roster = [
        u for u in approved
        if not u.is_archived
        and not u.is_blocked
        and getattr(lifecycle_by_user.get(u.id), "participation_mode", "ACTIVE") != "EXITED"
    ]
    zone = ZoneInfo(timezone_name)
    active_ids = set((await session.scalars(verified_users_between(
        datetime.combine(start_date, datetime.min.time(), tzinfo=zone),
        datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=zone),
    ))).all())
    active_base = [u for u in current_roster if u.id in active_ids]
    new_members = await count_new_members(session,
        datetime.combine(start_date, datetime.min.time(), tzinfo=zone),
        datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=zone))
    returned = [
        u for u in approved
        if _in_period(getattr(lifecycle_by_user.get(u.id), "returned_at", None), start_date, end_date)
    ]

    registrations = list((await session.scalars(select(EventRegistration))).all())
    project_members = list((await session.scalars(select(ProjectMember))).all())
    milestones = list((await session.scalars(select(ProjectMilestone))).all())
    tasks = list((await session.scalars(select(Task))).all())
    portfolio = list((await session.scalars(select(PortfolioItem))).all())
    rewards = list((await session.scalars(select(RewardRedemption))).all())
    decisions = list((await session.scalars(select(LeadershipAttentionItem))).all())

    period_events = [event for event in analytics.events if _in_period(event.event_date, start_date, end_date)]
    event_ids = {event.id for event in period_events}
    period_regs = [row for row in registrations if row.event_id in event_ids]
    attended = [row for row in period_regs if _enum(row.status) == "attended"]
    in_period = lambda value: _in_period(value, start_date, end_date, timezone_name)
    confirmed_members = [row for row in project_members if row.contribution_status == 'confirmed' and in_period(row.contribution_confirmed_at)]
    completed_milestones = [row for row in milestones if row.status == 'completed' and in_period(row.completed_at)]
    contributor_counts = Counter(row.project_id for row in confirmed_members)
    milestone_counts = Counter(row.project_id for row in completed_milestones)
    new_projects = [project for project in analytics.projects if in_period(project.created_at)]
    period_projects = [project for project in analytics.projects if in_period(project.created_at)
        or contributor_counts[project.id] or milestone_counts[project.id]]
    period_tasks = [task for task in tasks if in_period(task.created_at)]
    accepted_results = int(await session.scalar(select(func.count(func.distinct(TaskSubmission.id))).join(AuditLog,
        (AuditLog.entity_type == 'task_submission') & (AuditLog.entity_id == TaskSubmission.id)).where(
        TaskSubmission.status == 'approved', AuditLog.action == 'task.submission_approve',
        AuditLog.created_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=zone),
        AuditLog.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=zone))) or 0)

    wb = Workbook()
    wb.remove(wb.active)
    for title in SHEET_NAMES:
        ws = wb.create_sheet(title)
        ws.sheet_view.showGridLines = False

    summary_rows = [
        ["Профили со статусом «Одобрен»", len(approved), "Текущий статус approved, включая профили вне действующего состава; это не историческая когорта", "User.application_status"],
        ["Текущий состав", len(current_roster), "Одобрены, не archived/blocked и не EXITED", "ParticipationLifecycle"],
        ["Активная база", len(active_base), "Подтверждённые результаты за выбранный период; без цифровых баллов и должностей", "Verified activity facts"],
        ["Новые за период", new_members, "Первое одобрение по аудиту; исторически неполные записи не восстановлены", "AuditLog user.approved"],
        ["Вернулись за период", len(returned), "Зафиксированный возврат после снижения активности", "ParticipationLifecycle.returned_at"],
        ["События за период", len(period_events), "События с датой внутри выбранного периода", "Event.event_date"],
        ["Attendance rate", round(len(attended) * 100 / len(period_regs), 1) if period_regs else None, "Подтверждённые посещения / регистрации выбранных событий", "EventRegistration"],
        ["Проекты за период", len(period_projects), "Созданы или имеют подтверждённый вклад/завершённый этап в периоде", "Project + confirmations + milestones"],
        ["Создано проектов", len(new_projects), "Новые проекты за выбранные даты", "Project.created_at"],
        ["Создано заданий", len(period_tasks), "Новые задания за выбранные даты", "Task.created_at"],
        ["Подтверждённых посещений", len(attended), "Записи attended выбранных событий", "EventRegistration"],
        ["Verified task results", accepted_results, "Distinct approved результаты с audit принятия в выбранном периоде", "TaskSubmission + AuditLog"],
        ["Условный операционный индекс", efficiency.score if current_roster else None, efficiency.label if current_roster else "Нет базы для расчёта", "ERA efficiency: эвристика платформы, собственное окно 7/30 дней; не объективная оценка организации"],
        ["Пульс Мой вектор", health.pulse if health.pulse is not None else "—", health.pulse_label, "Безопасный агрегат; cohort suppression"],
    ]
    _summary_sheet(wb[SHEET_NAMES[0]], period_label=period_label, rows=summary_rows)

    _append_table(wb[SHEET_NAMES[1]], ["Показатель", "Количество"], [
        ["Текущий состав", len(current_roster)], ["С подтверждённым результатом за период", len(active_base)],
        ["Новые одобрения за период", new_members], ["Возвраты за период", len(returned)],
    ])

    rank_counts = Counter(_enum(user.participation_status) for user in current_roster)
    state_counts = Counter(getattr(lifecycle_by_user.get(user.id), "activity_state", "ADAPTATION") for user in current_roster)
    growth_rows = [["Ранг", key, value] for key, value in rank_counts.items()]
    growth_rows += [["Activity State", key, value] for key, value in state_counts.items()]
    growth_rows += [["Период", "Новые", new_members], ["Период", "Вернулись", len(returned)]]
    _append_table(wb[SHEET_NAMES[2]], ["Срез", "Этап", "Количество"], growth_rows)

    _append_table(
        wb[SHEET_NAMES[3]],
        ["Департамент", "Участников", "Активных целей", "Выполнено целей"],
        [[row.name, row.members, row.active_goals, row.done_goals] for row in analytics.department_stats],
    )
    _append_table(
        wb[SHEET_NAMES[4]],
        ["Департамент", "Направление", "Участников"],
        [[row.department, row.name, row.members] for row in analytics.direction_stats],
    )

    vector_rows = [
        ["Coverage", health.pulse_coverage, f"n={health.pulse_sample_size}", "minimum cohort применяется до расчёта"],
        ["Pulse", health.pulse if health.pulse is not None else "—", health.pulse_label, "не используется для rank/certificates/leadership decisions"],
    ]
    for item in health.vector_dimensions:
        vector_rows.append([item.label, item.value, item.delta if item.delta is not None else "—", "агрегат; не индивидуальная оценка"])
    _append_table(wb[SHEET_NAMES[5]], ["Показатель", "Значение", "Изменение / выборка", "Privacy note"], vector_rows)

    reg_counts: Counter[int] = Counter(row.event_id for row in period_regs)
    attended_counts: Counter[int] = Counter(row.event_id for row in attended)
    event_rows = []
    for event in period_events:
        total = reg_counts.get(event.id, 0)
        came = attended_counts.get(event.id, 0)
        event_rows.append([event.title, event.event_date, _enum(event.status), total, came, round(came * 100 / total, 1) if total else None])
    _append_table(wb[SHEET_NAMES[6]], ["Событие", "Дата", "Статус", "Регистраций", "Посетили", "Attendance, %"], event_rows)

    _append_table(
        wb[SHEET_NAMES[7]],
        ["Проект", "Текущий статус", "Создан", "Подтверждённых вкладов за период", "Завершено этапов за период", "Основание включения"],
        [[project.title, _enum(project.status), _date_of(project.created_at, timezone_name), contributor_counts[project.id],
          milestone_counts[project.id], 'Новый проект' if in_period(project.created_at) else 'Подтверждённая работа за период']
         for project in sorted(period_projects, key=lambda item: (str(item.created_at), item.id), reverse=True)],
    )

    task_rows = []
    for task in period_tasks:
        task_rows.append([task.title, _enum(task.status), _date_of(task.created_at), _date_of(task.deadline), getattr(task, "points", 0), "командное" if getattr(task, "team_mode", None) == "TEAM" else "обычное"])
    _append_table(wb[SHEET_NAMES[8]], ["Задание", "Статус", "Создано", "Дедлайн", "Баллы", "Тип"], task_rows)

    reward_counts = Counter(_enum(row.status) for row in rewards if in_period(row.created_at))
    _append_table(wb[SHEET_NAMES[9]], ["Статус заявки", "Количество"], [[key, count] for key, count in sorted(reward_counts.items())])

    portfolio_counts = Counter()
    for item in portfolio:
        if not _in_period(item.created_at, start_date, end_date) and not _in_period(getattr(item, "issued_at", None), start_date, end_date):
            continue
        portfolio_counts[(_enum(item.item_type), _enum(item.status))] += 1
    _append_table(wb[SHEET_NAMES[10]], ["Тип достижения", "Статус", "Количество"], [[kind, status, count] for (kind, status), count in sorted(portfolio_counts.items())])

    decision_rows = []
    for item in decisions:
        if not _in_period(item.created_at, start_date, end_date):
            continue
        decision_rows.append([_enum(item.type), _enum(item.severity), _enum(item.scope_type), _enum(item.status), _date_of(item.created_at)])
    _append_table(wb[SHEET_NAMES[11]], ["Сигнал / решение", "Критичность", "Область", "Статус", "Дата"], decision_rows)

    method_rows = [
        ["Период отчёта", period_label, "Фильтр применяется к временным сущностям; current roster/Active Base показываются на дату формирования."],
        ["Active Base", "Meaningful Activity + ACTIVE/LIGHT", "Не считается по login, просмотру, daily points, регистрации, должности или нахождению в департаменте."],
        ["Ранг", "ParticipationStatus", "Ранг ≠ должность и не определяется только total points."],
        ["Verified result", "Только подтверждённый результат", "Task/Event/Project scoring идёт через единый idempotent verified-activity gateway."],
        ["Мой вектор", "Aggregate only", "Raw ответы, personal notes и индивидуальные психологические оценки в workbook не попадают."],
        ["Technical IDs", "Не экспортируются", "В таблицах используются названия/имена; database ids и Telegram numeric ids скрыты по умолчанию."],
        ["Персональные данные", "Только обезличенные итоги", "Списки людей, имена, контакты, анкеты и индивидуальное портфолио исключены из общего PDF/Excel."],
    ]
    _append_table(wb[SHEET_NAMES[12]], ["Правило", "Как считается", "Ограничение / смысл"], method_rows)

    for ws in wb.worksheets:
        # This report contains facts, never Excel formulas. User-provided names
        # and titles starting with '=' must remain text in both XLSX and PDF.
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
        ws.sheet_view.showGridLines = False
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0

    output = BytesIO()
    wb.save(output)
    return output.getvalue()
