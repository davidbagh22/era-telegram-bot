from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time
from io import BytesIO
from typing import Any


def _plain(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, date):
        return value
    return value


def _value(item: Any, key: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _label(value: Any, labels: dict[Any, str]) -> str:
    return labels.get(value, labels.get(str(value), str(value or "—")))


def build_analytics_workbook(
    users,
    events,
    projects,
    point_totals: dict[int, int],
    *,
    department_stats: Iterable[Any] = (),
    direction_stats: Iterable[Any] = (),
    goals: Iterable[Any] = (),
    contacts: Iterable[Any] = (),
    sections: set[str] | None = None,
) -> bytes:
    """Build a polished Russian Excel workbook for ERA administration.

    The function keeps the old four positional arguments for compatibility, while
    allowing admin screens to request richer sheets and filtered downloads.
    """

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.worksheet.table import Table, TableStyleInfo
    from openpyxl.utils import get_column_letter

    from app.utils.constants import (
        APPLICATION_STATUS_LABELS,
        EVENT_STATUS_LABELS,
        PROJECT_STATUS_LABELS,
        ROLE_LABELS,
        STATUS_LABELS,
    )

    sections = sections or {
        "summary",
        "users",
        "departments",
        "directions",
        "events",
        "projects",
        "goals",
        "contacts",
    }
    users = list(users)
    events = list(events)
    projects = list(projects)
    department_stats = list(department_stats)
    direction_stats = list(direction_stats)
    goals = list(goals)
    contacts = list(contacts)

    wb = Workbook()
    accent = "7C27C9"
    red = "EC2533"
    light = "F7EDF9"
    border = Border(bottom=Side(style="thin", color="E4DCE7"))

    def style_sheet(ws) -> None:
        ws.freeze_panes = "A2"
        ws.sheet_view.showGridLines = False
        if ws.max_row > 1 and ws.max_column > 0:
            ref = f"A1:{get_column_letter(ws.max_column)}{ws.max_row}"
            ws.auto_filter.ref = ref
            table = Table(displayName=("tbl_" + ws.title.replace(" ", "_"))[:30], ref=ref)
            table.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium4",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False,
            )
            ws.add_table(table)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=accent)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
        for column in range(1, ws.max_column + 1):
            letter = get_column_letter(column)
            width = max(
                len(str(ws.cell(row, column).value or ""))
                for row in range(1, ws.max_row + 1)
            )
            ws.column_dimensions[letter].width = min(max(width + 3, 12), 55)

    def append_sheet(title: str, headers: list[str], rows: list[list[Any]]):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for row in rows:
            ws.append([_plain(value) for value in row])
        style_sheet(ws)
        return ws

    # Remove default after creating our first real sheet.
    default = wb.active
    wb.remove(default)

    if "summary" in sections:
        ws = wb.create_sheet("Сводка")
        approved = sum(1 for u in users if str(getattr(u, "application_status", "")) == "approved")
        total_points_value = sum(point_totals.values())
        cards = [
            ("Участники", len(users)),
            ("Одобрены", approved),
            ("Мероприятия", len(events)),
            ("Проекты", len(projects)),
            ("Баллы всего", total_points_value),
            ("Средний баланс", round(total_points_value / len(users), 1) if users else 0),
        ]
        ws.append(["Показатель", "Значение"])
        for row in cards:
            ws.append(list(row))
        ws.append([])
        ws.append(["Топ-5 активистов", "Баллы"])
        leaders = sorted(users, key=lambda u: point_totals.get(u.id, 0), reverse=True)[:5]
        for member in leaders:
            ws.append([
                f"{member.first_name} {member.last_name or ''}".strip(),
                point_totals.get(member.id, 0),
            ])
        for row in ws.iter_rows():
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=red)
        ws.column_dimensions["A"].width = 34
        ws.column_dimensions["B"].width = 18
        ws.sheet_view.showGridLines = False

    if "users" in sections:
        append_sheet(
            "Участники",
            [
                "Имя",
                "Фамилия",
                "Telegram",
                "Возраст",
                "Город",
                "Email",
                "Роль",
                "Статус участия",
                "Статус заявки",
                "Баллы",
                "Дата регистрации",
            ],
            [
                [
                    user.first_name,
                    user.last_name or "",
                    f"@{user.username}" if user.username else str(user.telegram_id),
                    user.age,
                    user.city or "",
                    user.email or "",
                    _label(user.role, ROLE_LABELS),
                    _label(user.participation_status, STATUS_LABELS),
                    _label(user.application_status, APPLICATION_STATUS_LABELS),
                    point_totals.get(user.id, 0),
                    user.created_at,
                ]
                for user in users
            ],
        )

    if "departments" in sections:
        append_sheet(
            "Департаменты",
            ["Департамент", "Участников", "Активных целей", "Выполнено целей"],
            [
                [
                    _value(item, "name"),
                    _value(item, "members", 0),
                    _value(item, "active_goals", 0),
                    _value(item, "done_goals", 0),
                ]
                for item in department_stats
            ],
        )

    if "directions" in sections:
        append_sheet(
            "Направления",
            ["Департамент", "Направление", "Участников"],
            [
                [
                    _value(item, "department"),
                    _value(item, "name"),
                    _value(item, "members", 0),
                ]
                for item in direction_stats
            ],
        )

    if "events" in sections:
        append_sheet(
            "Мероприятия",
            ["Название", "Дата", "Время", "Место", "Формат", "Статус", "Лимит", "Баллы"],
            [
                [
                    event.title,
                    event.event_date,
                    event.event_time,
                    event.location,
                    event.format,
                    _label(event.status, EVENT_STATUS_LABELS),
                    event.participant_limit,
                    event.points_for_visit,
                ]
                for event in events
            ],
        )

    if "projects" in sections:
        append_sheet(
            "Проекты",
            ["Название", "Автор ID", "Статус", "Площадка", "Дата", "Время", "Создан"],
            [
                [
                    project.title,
                    project.author_id,
                    _label(project.status, PROJECT_STATUS_LABELS),
                    project.venue_status,
                    project.proposed_date,
                    project.proposed_time,
                    project.created_at,
                ]
                for project in projects
            ],
        )

    if "goals" in sections:
        append_sheet(
            "Цели месяца",
            ["Месяц", "Уровень", "Название", "План", "Факт", "Статус", "Срок"],
            [
                [
                    _value(goal, "month"),
                    _value(goal, "scope_name", _value(goal, "scope_type")),
                    _value(goal, "title"),
                    _value(goal, "target_value", 0),
                    _value(goal, "current_value", 0),
                    _value(goal, "status"),
                    _value(goal, "due_date"),
                ]
                for goal in goals
            ],
        )

    if "contacts" in sections:
        append_sheet(
            "Организации",
            ["Организация", "Контакт", "Должность", "Второй контакт", "Должность 2", "Почта", "Телефон", "Заметки"],
            [
                [
                    contact.organization_name,
                    contact.contact_name or "",
                    contact.position or "",
                    contact.second_contact_name or "",
                    contact.second_position or "",
                    contact.email or "",
                    contact.phone or "",
                    contact.notes or "",
                ]
                for contact in contacts
            ],
        )

    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()
