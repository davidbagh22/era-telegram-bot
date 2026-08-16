from __future__ import annotations

from datetime import date
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Iterable

from app.database.career_models import CareerPortfolioItem, CareerProfile, RecommendationRequest
from app.database.models import User
from app.services.portfolio_service import PortfolioData, PortfolioEntry

LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "era_logo.jpg"
CHAIR_LABEL = "Председатель Багдасарян Д.С."
DEPUTY_LABEL = "Заместитель Карапетян Е.А."

PURPOSE_LABELS = {
    "work": "Работа",
    "internship": "Стажировка",
    "university": "Университет",
    "grant": "Грант / конкурс",
    "volunteer": "Волонтёрская программа",
    "universal": "Универсальное",
}

TYPE_LABELS = {
    "education": "Образование",
    "work": "Опыт работы",
    "internship": "Стажировки",
    "project": "Проекты",
    "achievement": "Достижения",
    "certificate": "Сертификаты",
    "course": "Курсы",
    "publication": "Публикации",
    "speech": "Выступления",
    "volunteer": "Волонтёрство",
    "award": "Награды",
    "language": "Языки",
    "skill": "Навыки",
    "other": "Дополнительно",
}

PURPOSE_ORDER = {
    "work": ["work", "internship", "project", "achievement", "education", "certificate", "course", "volunteer", "publication", "speech", "other"],
    "internship": ["education", "project", "internship", "achievement", "certificate", "course", "volunteer", "work", "publication", "speech", "other"],
    "university": ["education", "achievement", "project", "volunteer", "certificate", "course", "publication", "speech", "work", "other"],
    "grant": ["achievement", "project", "volunteer", "award", "certificate", "education", "publication", "speech", "work", "other"],
    "volunteer": ["volunteer", "project", "achievement", "education", "certificate", "course", "work", "other"],
    "universal": ["work", "education", "project", "achievement", "certificate", "volunteer", "internship", "course", "publication", "speech", "award", "other"],
}


def _full_name(user: User) -> str:
    return " ".join(part for part in (user.first_name, user.last_name) if part).strip() or "Участник ЭРА"


def _value(value: str | None) -> str:
    return (value or "").strip()


def _font_path() -> Path:
    candidates = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    )
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        raise RuntimeError("Unicode font for ERA documents is unavailable")
    return path


def _register_font() -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if "ERAUnicode" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("ERAUnicode", str(_font_path())))


def _styles():
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    return {
        "hero": ParagraphStyle(
            "CareerHero",
            parent=base["Title"],
            fontName="ERAUnicode",
            fontSize=23,
            leading=27,
            textColor=colors.HexColor("#17151B"),
            alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "eyebrow": ParagraphStyle(
            "CareerEyebrow",
            parent=base["Normal"],
            fontName="ERAUnicode",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#8E229B"),
            alignment=TA_LEFT,
            spaceAfter=5,
        ),
        "headline": ParagraphStyle(
            "CareerHeadline",
            parent=base["Normal"],
            fontName="ERAUnicode",
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#5B5661"),
            alignment=TA_LEFT,
            spaceAfter=6,
        ),
        "section": ParagraphStyle(
            "CareerSection",
            parent=base["Heading2"],
            fontName="ERAUnicode",
            fontSize=12.5,
            leading=16,
            textColor=colors.HexColor("#E5262E"),
            spaceBefore=10,
            spaceAfter=6,
        ),
        "item": ParagraphStyle(
            "CareerItem",
            parent=base["BodyText"],
            fontName="ERAUnicode",
            fontSize=9.4,
            leading=13.5,
            textColor=colors.HexColor("#252229"),
            spaceAfter=5,
        ),
        "small": ParagraphStyle(
            "CareerSmall",
            parent=base["BodyText"],
            fontName="ERAUnicode",
            fontSize=7.6,
            leading=10.5,
            textColor=colors.HexColor("#6E6873"),
        ),
        "center": ParagraphStyle(
            "CareerCenter",
            parent=base["BodyText"],
            fontName="ERAUnicode",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#252229"),
            alignment=TA_CENTER,
        ),
        "letter": ParagraphStyle(
            "CareerLetter",
            parent=base["BodyText"],
            fontName="ERAUnicode",
            fontSize=10.4,
            leading=16.5,
            textColor=colors.HexColor("#252229"),
            alignment=TA_LEFT,
            spaceAfter=9,
        ),
    }


def _header_story(styles, title: str, subtitle: str):
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors

    if not LOGO_PATH.exists():
        raise RuntimeError("ERA logo asset is unavailable")
    logo = Image(str(LOGO_PATH), width=34 * mm, height=34 * mm)
    text = [
        Paragraph("ОБЪЕДИНЕНИЕ ЛИДЕРОВ И КУЛЬТУРНЫХ ИНИЦИАТИВ", styles["eyebrow"]),
        Paragraph(escape(title), styles["hero"]),
        Paragraph(escape(subtitle), styles["headline"]),
    ]
    table = Table([[logo, text]], colWidths=[40 * mm, 126 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LINEBELOW", (0, 0), (-1, -1), 1.1, colors.HexColor("#EF3340")),
            ]
        )
    )
    return [table, Spacer(1, 5 * mm)]


def _signature_story(styles, *, verified_note: bool):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

    rows = [
        ["Председатель", "________________________", "Багдасарян Д.С."],
        ["Заместитель председателя", "________________________", "Карапетян Е.А."],
        ["М.П.", "________________________", ""],
    ]
    table = Table(rows, colWidths=[48 * mm, 57 * mm, 60 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "ERAUnicode"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#2A262D")),
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    note = (
        "Подписи и печать подтверждают только сведения, отмеченные в документе как «Подтверждено ЭРА». "
        "Данные с пометкой «Добавлено участником» включены по заявлению владельца портфолио."
        if verified_note
        else "Место для подписей уполномоченных лиц и печати организации."
    )
    return KeepTogether(
        [
            Spacer(1, 10 * mm),
            Paragraph(escape(note), styles["small"]),
            Spacer(1, 7 * mm),
            table,
        ]
    )


def _career_item_html(item: CareerPortfolioItem) -> str:
    meta = [part for part in (item.organization, item.issued_at.strftime("%d.%m.%Y") if item.issued_at else None) if part]
    status = "✓ Подтверждено ЭРА" if item.status == "verified" else "Добавлено участником"
    details = escape(item.description or "")
    return (
        f"<b>{escape(item.title)}</b>"
        f"{(' · ' + escape(' · '.join(meta))) if meta else ''}<br/>"
        f"<font color={'#8E229B' if item.status == 'verified' else '#77717B'}>{escape(status)}</font>"
        f"{('<br/>' + details) if details else ''}"
    )


def _legacy_entry_html(item: PortfolioEntry, label: str = "✓ Подтверждено ЭРА") -> str:
    meta = " · ".join(part for part in (item.date_label, item.status) if part)
    desc = item.description or item.category
    return (
        f"<b>{escape(item.title)}</b>{(' · ' + escape(meta)) if meta else ''}<br/>"
        f"<font color='#8E229B'>{escape(label)}</font>"
        f"{('<br/>' + escape(desc)) if desc else ''}"
    )


def _confirmed_era_sections(portfolio: PortfolioData) -> dict[str, list[PortfolioEntry]]:
    approved_projects = [
        item for item in portfolio.projects
        if item.status in {"Одобрен", "В работе", "Завершён", "вклад подтверждён"}
    ]
    attended_events = [item for item in portfolio.events if item.status == "Посетил"]
    completed_tasks = [
        item for item in portfolio.tasks
        if item.status in {"Выполнена", "approved", "completed", "подтверждено"}
    ]
    return {
        "project": approved_projects,
        "event": attended_events,
        "task": completed_tasks,
        "leadership": portfolio.leadership,
        "certificate": portfolio.certificates,
        "achievement": portfolio.badges,
        "volunteer": [
            item for item in portfolio.volunteer
            if item.status in {"Выполнена", "approved", "completed", "подтверждено"}
        ],
    }


def build_career_resume(
    user: User,
    career_profile: CareerProfile,
    portfolio: PortfolioData,
    items: list[CareerPortfolioItem],
    *,
    purpose: str,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    _register_font()
    styles = _styles()
    stream = BytesIO()
    document = SimpleDocTemplate(
        stream,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Резюме — {_full_name(user)}",
        author="Объединение лидеров и культурных инициатив (ЭРА)",
    )
    headline = _value(career_profile.headline) or _value(user.occupation) or portfolio.participation_status
    story = _header_story(
        styles,
        _full_name(user),
        f"Резюме · {PURPOSE_LABELS.get(purpose, PURPOSE_LABELS['universal'])}",
    )

    contact = " · ".join(
        value for value in (_value(user.city), _value(user.email), f"Telegram ID {user.telegram_id}") if value
    )
    if headline:
        story.append(Paragraph(escape(headline), styles["headline"]))
    if contact:
        story.append(Paragraph(escape(contact), styles["small"]))

    about = _value(career_profile.about) or _value(user.experience)
    if about:
        story.extend([Paragraph("О себе", styles["section"]), Paragraph(escape(about), styles["item"])])

    skills = [_value(item) for item in (user.skills or []) if _value(item)][:8]
    if skills:
        story.extend(
            [
                Paragraph("Ключевые компетенции", styles["section"]),
                Paragraph(escape(" · ".join(skills)), styles["item"]),
            ]
        )

    user_items = [item for item in items if item.include_in_resume and item.status != "pending"]
    grouped: dict[str, list[CareerPortfolioItem]] = {}
    for item in user_items:
        grouped.setdefault(item.item_type, []).append(item)
    legacy = _confirmed_era_sections(portfolio)

    order = PURPOSE_ORDER.get(purpose, PURPOSE_ORDER["universal"])
    shown_types: set[str] = set()
    for item_type in order:
        own = grouped.get(item_type, [])
        era = legacy.get(item_type, [])
        if not own and not era:
            continue
        shown_types.add(item_type)
        story.append(Paragraph(TYPE_LABELS.get(item_type, item_type.title()), styles["section"]))
        for entry in era:
            story.append(Paragraph(_legacy_entry_html(entry), styles["item"]))
        for entry in own:
            story.append(Paragraph(_career_item_html(entry), styles["item"]))

    for item_type, own in grouped.items():
        if item_type in shown_types or not own:
            continue
        story.append(Paragraph(TYPE_LABELS.get(item_type, item_type.title()), styles["section"]))
        for entry in own:
            story.append(Paragraph(_career_item_html(entry), styles["item"]))

    if portfolio.education_work and not grouped.get("education"):
        story.extend(
            [
                Paragraph("Образование / занятость", styles["section"]),
                Paragraph(escape(portfolio.education_work), styles["item"]),
            ]
        )

    languages = career_profile.languages or []
    if languages:
        text = " · ".join(
            f"{_value(str(item.get('name')))}{(' — ' + _value(str(item.get('level')))) if _value(str(item.get('level'))) else ''}"
            for item in languages
            if _value(str(item.get("name")))
        )
        if text:
            story.extend([Paragraph("Языки", styles["section"]), Paragraph(escape(text), styles["item"])])

    era_counts = {
        "мероприятий": len(legacy["event"]),
        "проектов / вкладов": len(legacy["project"]),
        "задач": len(legacy["task"]),
        "лидерских ролей": len(legacy["leadership"]),
    }
    metrics = [[label, str(value)] for label, value in era_counts.items() if value]
    if metrics:
        story.append(Paragraph("Подтверждённая активность в ЭРА", styles["section"]))
        metrics_table = Table(metrics, colWidths=[92 * mm, 25 * mm], hAlign="LEFT")
        metrics_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "ERAUnicode"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#38323D")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAF6FA")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E7DDE8")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#EFE7F0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.extend([metrics_table, Spacer(1, 3 * mm)])

    story.append(_signature_story(styles, verified_note=True))
    document.build(story)
    return stream.getvalue()


def _qr_flowable(url: str):
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing

    qr = QrCodeWidget(url)
    bounds = qr.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    size = 78
    drawing = Drawing(size, size, transform=[size / width, 0, 0, size / height, 0, 0])
    drawing.add(qr)
    return drawing


def build_official_recommendation(
    user: User,
    request: RecommendationRequest,
    *,
    verification_url: str,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    if request.status != "approved" or not request.document_number:
        raise ValueError("recommendation_not_approved")
    _register_font()
    styles = _styles()
    stream = BytesIO()
    document = SimpleDocTemplate(
        stream,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Рекомендательное письмо — {_full_name(user)}",
        author="Объединение лидеров и культурных инициатив (ЭРА)",
    )
    issue_date = request.approved_at.date() if request.approved_at else date.today()
    story = _header_story(styles, "Рекомендательное письмо", _full_name(user))
    meta = Table(
        [
            ["Документ", request.document_number],
            ["Дата", issue_date.strftime("%d.%m.%Y")],
            ["Назначение", PURPOSE_LABELS.get(request.purpose, PURPOSE_LABELS["universal"])],
        ],
        colWidths=[36 * mm, 112 * mm],
    )
    meta.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "ERAUnicode"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#8E229B")),
                ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#2A262D")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([meta, Spacer(1, 7 * mm)])
    text = request.final_text or request.draft_text
    for paragraph in [part.strip() for part in text.split("\n") if part.strip()] or [text]:
        story.append(Paragraph(escape(paragraph), styles["letter"]))

    verify_table = Table(
        [
            [
                _qr_flowable(verification_url),
                [
                    Paragraph("Проверка документа", styles["section"]),
                    Paragraph(
                        "QR ведёт на страницу проверки номера и даты выдачи. "
                        "Содержание личного портфолио в публичной проверке не раскрывается.",
                        styles["small"],
                    ),
                    Paragraph(f"ID: {escape(request.document_number)}", styles["small"]),
                ],
            ]
        ],
        colWidths=[31 * mm, 112 * mm],
    )
    verify_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAF6FA")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E7DDE8")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([Spacer(1, 5 * mm), verify_table, _signature_story(styles, verified_note=False)])
    document.build(story)
    return stream.getvalue()
