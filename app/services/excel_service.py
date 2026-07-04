from __future__ import annotations

from datetime import datetime
from io import BytesIO


ROLE_LABELS = {
    "participant": "Участник",
    "activist": "Активист",
    "leader": "Лидер",
    "head": "Руководитель",
    "council": "Совет",
    "admin": "Администратор",
}
USER_STATUS_LABELS = {
    "new_member": "Новый участник",
    "involved_member": "Вовлечённый участник",
    "active_member": "Активный участник",
    "team_member": "Член команды",
    "project_curator": "Куратор проекта",
    "community_leader": "Лидер сообщества",
}
EVENT_STATUS_LABELS = {
    "draft": "Черновик",
    "pending_approval": "На согласовании",
    "approved": "Одобрено",
    "published": "Опубликовано",
    "registration_open": "Регистрация открыта",
    "registration_closed": "Регистрация закрыта",
    "active": "Идёт сейчас",
    "completed": "Завершено",
    "cancelled": "Отменено",
}
PROJECT_STATUS_LABELS = {
    "draft": "Черновик",
    "pending_review": "На рассмотрении",
    "initial_review": "Первичная проверка",
    "venue_review": "Согласование площадки",
    "needs_revision": "Нужна доработка",
    "approved": "Одобрен",
    "in_progress": "В работе",
    "completed": "Завершён",
    "rejected": "Отклонён",
    "postponed": "Перенесён",
    "cancelled": "Отменён",
}


def _plain(value):
    return value.value if hasattr(value, "value") else value


def _label(mapping: dict[str, str], value) -> str:
    raw = str(_plain(value) or "")
    return mapping.get(raw, raw or "—")


def _naive(value):
    if value is None:
        return None
    return value.replace(tzinfo=None) if getattr(value, "tzinfo", None) else value


def build_analytics_workbook(
    users,
    events,
    projects,
    point_totals: dict[int, int],
    *,
    department_stats=(),
    direction_stats=(),
    goals=(),
    contacts=(),
    sections: set[str] | None = None,
) -> bytes:
    """Create a readable Russian management workbook for ERA."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.worksheet.table import Table, TableStyleInfo
    from openpyxl.utils import get_column_letter

    selected = sections or {
        "summary",
        "users",
        "departments",
        "directions",
        "events",
        "projects",
        "goals",
        "contacts",
    }
    workbook = Workbook()
    workbook.remove(workbook.active)

    purple = "7C27C9"
    red = "EC2533"
    pale = "F7F1FA"
    pale_red = "FDECEF"
    dark = "29242D"
    light_border = Side(style="thin", color="E6DDE9")

    def prepare(sheet, title: str, subtitle: str, headers: list[str], rows: list[list], table_name: str):
        sheet.sheet_view.showGridLines = False
        sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(1, len(headers)))
        title_cell = sheet.cell(1, 1, title)
        title_cell.font = Font(name="Aptos Display", size=18, bold=True, color="FFFFFF")
        title_cell.fill = PatternFill("solid", fgColor=purple)
        title_cell.alignment = Alignment(vertical="center")
        sheet.row_dimensions[1].height = 30

        sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(1, len(headers)))
        subtitle_cell = sheet.cell(2, 1, subtitle)
        subtitle_cell.font = Font(name="Aptos", size=10, color="6B6270")
        subtitle_cell.fill = PatternFill("solid", fgColor=pale)
        subtitle_cell.alignment = Alignment(wrap_text=True, vertical="center")
        sheet.row_dimensions[2].height = 28

        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        header_row = 3
        for cell in sheet[header_row]:
            cell.font = Font(name="Aptos", bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=red)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        sheet.row_dimensions[header_row].height = 30
        sheet.freeze_panes = "A4"
        sheet.auto_filter.ref = f"A3:{get_column_letter(len(headers))}{max(3, sheet.max_row)}"

        if rows:
            table = Table(
                displayName=table_name,
                ref=f"A3:{get_column_letter(len(headers))}{sheet.max_row}",
            )
            table.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium4",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False,
            )
            sheet.add_table(table)

        for row in sheet.iter_rows(min_row=4):
            for cell in row:
                cell.font = Font(name="Aptos", size=10, color=dark)
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.border = Border(bottom=light_border)

        for column in range(1, len(headers) + 1):
            values = [headers[column - 1]] + [
                str(row[column - 1] or "") for row in rows[:300]
            ]
            width = min(max(max(len(value) for value in values) + 2, 12), 38)
            sheet.column_dimensions[get_column_letter(column)].width = width

    if "summary" in selected:
        sheet = workbook.create_sheet("Сводка")
        sheet.sheet_view.showGridLines = False
        sheet.merge_cells("A1:F1")
        sheet["A1"] = "ЭРА · управленческая аналитика"
        sheet["A1"].font = Font(name="Aptos Display", size=20, bold=True, color="FFFFFF")
        sheet["A1"].fill = PatternFill("solid", fgColor=purple)
        sheet["A1"].alignment = Alignment(vertical="center")
        sheet.row_dimensions[1].height = 34
        sheet.merge_cells("A2:F2")
        sheet["A2"] = f"Сформировано {datetime.now().astimezone():%d.%m.%Y %H:%M}"
        sheet["A2"].font = Font(name="Aptos", color="6B6270")
        sheet["A2"].fill = PatternFill("solid", fgColor=pale)
        sheet["A2"].alignment = Alignment(vertical="center")

        completed_events = sum(str(_plain(x.status)) == "completed" for x in events)
        completed_projects = sum(str(_plain(x.status)) == "completed" for x in projects)
        cards = [
            ("Участники", len(users)),
            ("Баллы", sum(point_totals.values())),
            ("Мероприятия", len(events)),
            ("Завершено мероприятий", completed_events),
            ("Проекты", len(projects)),
            ("Завершено проектов", completed_projects),
        ]
        for index, (label, value) in enumerate(cards):
            row = 4 + (index // 3) * 3
            col = 1 + (index % 3) * 2
            sheet.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col + 1)
            sheet.cell(row, col, label)
            sheet.cell(row, col).font = Font(name="Aptos", bold=True, color=purple)
            sheet.cell(row, col).fill = PatternFill("solid", fgColor=pale)
            sheet.merge_cells(start_row=row + 1, start_column=col, end_row=row + 1, end_column=col + 1)
            sheet.cell(row + 1, col, value)
            sheet.cell(row + 1, col).font = Font(name="Aptos Display", size=18, bold=True, color=red)
            sheet.cell(row + 1, col).fill = PatternFill("solid", fgColor=pale_red)

        sheet["A11"] = "Топ-5 активистов"
        sheet["A11"].font = Font(name="Aptos Display", size=14, bold=True, color=purple)
        top_users = sorted(users, key=lambda x: point_totals.get(x.id, 0), reverse=True)[:5]
        sheet.append(["Место", "Участник", "Роль", "Баллы"])
        for place, user in enumerate(top_users, 1):
            sheet.append([
                place,
                f"{user.first_name} {user.last_name or ''}".strip(),
                _label(ROLE_LABELS, user.role),
                point_totals.get(user.id, 0),
            ])
        for cell in sheet[12]:
            cell.font = Font(name="Aptos", bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=red)
        sheet.freeze_panes = "A12"
        for col, width in {"A": 14, "B": 32, "C": 24, "D": 14, "E": 18, "F": 18}.items():
            sheet.column_dimensions[col].width = width

    if "users" in selected:
        rows = []
        for user in users:
            departments = ", ".join(x.department.name for x in getattr(user, "departments", []) if getattr(x, "department", None))
            directions = ", ".join(x.direction.name for x in getattr(user, "directions", []) if getattr(x, "direction", None))
            rows.append([
                user.first_name,
                user.last_name or "",
                f"@{user.username}" if user.username else "",
                user.age,
                user.city or "",
                user.email or "",
                user.phone or "",
                _label(ROLE_LABELS, user.role),
                _label(USER_STATUS_LABELS, user.participation_status),
                departments,
                directions,
                point_totals.get(user.id, 0),
                _naive(user.created_at),
            ])
        sheet = workbook.create_sheet("Участники")
        prepare(
            sheet,
            "Участники ЭРА",
            "Актуальная база участников с ролями, направлениями и баллами",
            ["Имя", "Фамилия", "Telegram", "Возраст", "Город", "Почта", "Телефон", "Роль", "Статус", "Департаменты", "Направления", "Баллы", "Дата регистрации"],
            rows,
            "EraUsers",
        )
        sheet.column_dimensions["M"].width = 20
        for cell in sheet["M"][3:]:
            cell.number_format = "dd.mm.yyyy hh:mm"

    if "departments" in selected:
        rows = [[
            item.get("name", "—"), item.get("members", 0), item.get("directions", 0),
            item.get("projects", 0), item.get("events", 0), item.get("tasks_completed", 0),
            item.get("goals_active", 0), item.get("goals_completed", 0),
        ] for item in department_stats]
        prepare(
            workbook.create_sheet("Департаменты"),
            "Работа департаментов",
            "Состав, проекты, мероприятия, выполненные задачи и цели",
            ["Департамент", "Участники", "Направления", "Проекты", "Мероприятия", "Задачи выполнены", "Цели активные", "Цели выполнены"],
            rows,
            "EraDepartments",
        )

    if "directions" in selected:
        rows = [[
            item.get("department", "—"), item.get("name", "—"), item.get("members", 0),
            item.get("projects", 0), item.get("events", 0), item.get("tasks_completed", 0),
            item.get("goals_active", 0), item.get("goals_completed", 0),
        ] for item in direction_stats]
        prepare(
            workbook.create_sheet("Направления"),
            "Активность направлений",
            "Результаты каждого направления внутри департаментов",
            ["Департамент", "Направление", "Участники", "Проекты", "Мероприятия", "Задачи выполнены", "Цели активные", "Цели выполнены"],
            rows,
            "EraDirections",
        )

    if "events" in selected:
        rows = [[
            item.title, item.event_date, item.event_time.strftime("%H:%M"),
            item.location, _label(EVENT_STATUS_LABELS, item.status),
            item.participant_limit, item.points_for_visit,
        ] for item in events]
        sheet = workbook.create_sheet("Мероприятия")
        prepare(
            sheet,
            "Мероприятия ЭРА",
            "План и история мероприятий",
            ["Название", "Дата", "Время", "Место", "Статус", "Лимит", "Баллы"],
            rows,
            "EraEvents",
        )
        for cell in sheet["B"][3:]:
            cell.number_format = "dd.mm.yyyy"

    if "projects" in selected:
        rows = [[
            item.title, item.author_id, _label(PROJECT_STATUS_LABELS, item.status),
            item.venue_status or "—", item.proposed_date, item.proposed_time.strftime("%H:%M") if item.proposed_time else "",
            _naive(item.created_at),
        ] for item in projects]
        sheet = workbook.create_sheet("Проекты")
        prepare(
            sheet,
            "Проекты ЭРА",
            "Проекты участников и состояние согласования",
            ["Название", "Автор ID", "Статус", "Площадка", "Предложенная дата", "Время", "Создан"],
            rows,
            "EraProjects",
        )
        for cell in sheet["E"][3:]:
            cell.number_format = "dd.mm.yyyy"
        for cell in sheet["G"][3:]:
            cell.number_format = "dd.mm.yyyy hh:mm"

    if "goals" in selected:
        rows = [[
            goal.period, goal.scope_type, getattr(goal, "scope_name", "—"), goal.title,
            goal.metric, goal.target_value, goal.actual_value,
            round((goal.actual_value / goal.target_value) if goal.target_value else 0, 4),
            "Завершена" if goal.status == "completed" else "Активна",
            goal.notes or "",
        ] for goal in goals]
        sheet = workbook.create_sheet("Цели")
        prepare(
            sheet,
            "Ежемесячные цели",
            "План и фактическое выполнение департаментов и направлений",
            ["Месяц", "Уровень", "Подразделение", "Цель", "Показатель", "План", "Факт", "Выполнение", "Статус", "Комментарий"],
            rows,
            "EraGoals",
        )
        for cell in sheet["H"][3:]:
            cell.number_format = "0%"

    if "contacts" in selected:
        rows = [[
            item.organization or "", item.contact_name or "", item.position_primary or "",
            item.position_secondary or "", item.email or "", item.phone or "", item.notes or "",
        ] for item in contacts]
        prepare(
            workbook.create_sheet("Организации"),
            "База коллег и организаций",
            "Контактные данные партнёров и коллег ЭРА",
            ["Организация", "Контактное лицо", "Должность 1", "Должность 2", "Почта", "Телефон", "Комментарий"],
            rows,
            "EraContacts",
        )

    if not workbook.worksheets:
        workbook.create_sheet("Сводка")

    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()
