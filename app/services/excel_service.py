from io import BytesIO


def build_analytics_workbook(
    users, events, projects, point_totals: dict[int, int]
) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    users_sheet = workbook.active
    users_sheet.title = "Участники"
    users_sheet.append(
        [
            "Имя",
            "Фамилия",
            "Username",
            "Возраст",
            "Город",
            "Email",
            "Роль",
            "Статус",
            "Баллы",
            "Дата регистрации",
        ]
    )
    for user in users:
        users_sheet.append(
            [
                user.first_name,
                user.last_name or "",
                user.username or "",
                user.age,
                user.city or "",
                user.email or "",
                user.role,
                user.participation_status,
                point_totals.get(user.id, 0),
                user.created_at.replace(tzinfo=None) if user.created_at else None,
            ]
        )

    event_sheet = workbook.create_sheet("Мероприятия")
    event_sheet.append(["Название", "Дата", "Время", "Место", "Статус", "Лимит"])
    for event in events:
        event_sheet.append(
            [
                event.title,
                event.event_date,
                event.event_time.strftime("%H:%M"),
                event.location,
                event.status,
                event.participant_limit,
            ]
        )

    project_sheet = workbook.create_sheet("Проекты")
    project_sheet.append(["Название", "Автор ID", "Статус", "Площадка", "Создан"])
    for project in projects:
        project_sheet.append(
            [
                project.title,
                project.author_id,
                project.status,
                project.venue_status,
                project.created_at.replace(tzinfo=None) if project.created_at else None,
            ]
        )

    for sheet in workbook.worksheets:
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="7C27C9")
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in range(1, sheet.max_column + 1):
            width = max(
                len(str(sheet.cell(row, column).value or ""))
                for row in range(1, sheet.max_row + 1)
            )
            sheet.column_dimensions[get_column_letter(column)].width = min(
                width + 3, 45
            )

    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()
