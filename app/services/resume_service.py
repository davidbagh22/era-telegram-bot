from io import BytesIO
from html import escape
from pathlib import Path

from app.services.portfolio_service import PortfolioData, PortfolioEntry


def _value(text: str | None, fallback: str = "не указано") -> str:
    return escape((text or "").strip() or fallback)


def _list_value(items: list[str], fallback: str = "пока не выбраны") -> str:
    return escape(", ".join(item for item in items if item) or fallback)


def _entry_text(item: PortfolioEntry) -> str:
    meta = " · ".join(part for part in (item.date_label, item.status) if part)
    description = item.description or item.category
    if meta:
        return f"• <b>{escape(item.title)}</b> — {escape(meta)}<br/>{escape(description)}"
    return f"• <b>{escape(item.title)}</b><br/>{escape(description)}"


def _add_section(story: list, title: str, entries: list[PortfolioEntry], heading, body, spacer, *, empty: str) -> None:
    story.append(heading(title))
    if entries:
        for item in entries:
            story.append(body(_entry_text(item)))
            story.append(spacer())
    else:
        story.append(body(escape(empty)))


def build_era_resume(data: PortfolioData) -> bytes:
    """Build a compact branded PDF resume with a Unicode font."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    candidates = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    )
    font_path = next((path for path in candidates if path.exists()), None)
    if font_path is None:
        raise RuntimeError("Unicode font for the ERA resume is unavailable")
    pdfmetrics.registerFont(TTFont("ERAUnicode", str(font_path)))

    stream = BytesIO()
    document = SimpleDocTemplate(
        stream,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Резюме участника ЭРА",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "EraTitle",
        parent=styles["Title"],
        fontName="ERAUnicode",
        textColor=colors.HexColor("#EC2533"),
        alignment=TA_CENTER,
        fontSize=23,
        leading=28,
    )
    heading = ParagraphStyle(
        "EraHeading",
        parent=styles["Heading2"],
        fontName="ERAUnicode",
        textColor=colors.HexColor("#7C27C9"),
        fontSize=13,
        spaceBefore=10,
        spaceAfter=6,
    )
    body = ParagraphStyle(
        "EraBody",
        parent=styles["BodyText"],
        fontName="ERAUnicode",
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#28242D"),
    )
    small = ParagraphStyle(
        "EraSmall",
        parent=body,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#696171"),
        alignment=TA_LEFT,
    )

    def paragraph(text: str, style=body) -> Paragraph:
        return Paragraph(text, style)

    def section(text: str) -> Paragraph:
        return Paragraph(escape(text), heading)

    def spacer(height: float = 2) -> Spacer:
        return Spacer(1, height * mm)

    story = [
        Paragraph("ЭРА", title),
        Paragraph("ПОРТФОЛИО УЧАСТНИКА", title),
        Spacer(1, 6 * mm),
        Paragraph(escape(data.full_name), heading),
        paragraph(
            f"Роль: {_value(data.role)}<br/>"
            f"Статус роста: {_value(data.participation_status)}<br/>"
            f"Период участия: {_value(data.period)}<br/>"
            f"Город: {_value(data.city)}<br/>"
            f"Email: {_value(data.email)}"
        ),
        Spacer(1, 5 * mm),
    ]
    metrics = Table(
        [
            ["Баллы", "Мероприятия", "Проекты", "Задания"],
            [
                str(data.stats.get("points", 0)),
                str(data.stats.get("events", 0)),
                str(data.stats.get("projects", 0)),
                str(data.stats.get("tasks", 0)),
            ],
        ],
        colWidths=[40 * mm] * 4,
    )
    metrics.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "ERAUnicode"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FCECF3")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#7C27C9")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E4DCE7")),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend(
        [
            metrics,
            section("Профиль"),
            paragraph(
                f"Департамент: {_list_value(data.departments)}<br/>"
                f"Направление: {_list_value(data.directions)}<br/>"
                f"Учёба / работа: {_value(data.education_work)}<br/>"
                f"Занятость: {_value(data.occupation)}<br/>"
                f"Компетенции: {_list_value(data.skills, 'пока не указаны')}"
            ),
        ]
    )
    if data.experience:
        story.extend([section("Опыт до ЭРА"), paragraph(escape(data.experience))])
    _add_section(story, "Проекты", data.projects, section, paragraph, spacer, empty="Проектов пока нет")
    _add_section(story, "Мероприятия", data.events, section, paragraph, spacer, empty="Мероприятий пока нет")
    _add_section(story, "Задачи", data.tasks, section, paragraph, spacer, empty="Выполненных задач пока нет")
    _add_section(story, "Волонтёрская деятельность", data.volunteer, section, paragraph, spacer, empty="Волонтёрская активность пока не подтверждена")
    _add_section(story, "Лидерские роли", data.leadership, section, paragraph, spacer, empty="Лидерские роли пока не назначены")
    _add_section(story, "Достижения", data.confirmed_items, section, paragraph, spacer, empty="Подтверждённых достижений пока нет")
    _add_section(story, "Сертификаты", data.certificates, section, paragraph, spacer, empty="Сертификатов пока нет")
    _add_section(story, "Рекомендации", data.recommendations, section, paragraph, spacer, empty="Рекомендательных активностей пока нет")
    _add_section(story, "Знаки ЭРА", data.badges, section, paragraph, spacer, empty="Знаков пока нет")
    story.extend(
        [
            Spacer(1, 8 * mm),
            Paragraph(
                "Документ сформирован ботом общественной организации «ЭРА»",
                small,
            ),
        ]
    )
    document.build(story)
    return stream.getvalue()
