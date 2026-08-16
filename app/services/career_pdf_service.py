from __future__ import annotations

from datetime import date
from html import escape
from io import BytesIO
from pathlib import Path

from app.database.career_models import CareerPortfolioItem, CareerProfile, RecommendationRequest
from app.database.models import User
from app.services.portfolio_service import PortfolioData, PortfolioEntry

LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "era_logo.jpg"

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
    "award": "Награды",
    "certificate": "Сертификаты",
    "course": "Курсы",
    "publication": "Публикации",
    "speech": "Выступления",
    "volunteer": "Волонтёрство",
    "other": "Дополнительно",
}
PURPOSE_ORDER = {
    "work": ["work", "internship", "project", "achievement", "education", "certificate", "course", "volunteer", "publication", "speech", "other"],
    "internship": ["education", "project", "internship", "achievement", "certificate", "course", "volunteer", "work", "other"],
    "university": ["education", "achievement", "project", "volunteer", "certificate", "course", "publication", "speech", "work", "other"],
    "grant": ["achievement", "award", "project", "volunteer", "certificate", "education", "publication", "speech", "work", "other"],
    "volunteer": ["volunteer", "project", "achievement", "education", "certificate", "course", "work", "other"],
    "universal": ["work", "education", "project", "achievement", "award", "certificate", "volunteer", "internship", "course", "publication", "speech", "other"],
}


def _full_name(user: User) -> str:
    return " ".join(part for part in (user.first_name, user.last_name) if part).strip() or "Участник ЭРА"


def _font_path() -> Path:
    for candidate in (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ):
        if candidate.exists():
            return candidate
    raise RuntimeError("Unicode font for ERA documents is unavailable")


def _register_font() -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if "ERAUnicode" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("ERAUnicode", str(_font_path())))


def _document_styles():
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    return {
        "name": ParagraphStyle("EraName", parent=base["Title"], fontName="ERAUnicode", fontSize=22, leading=26, textColor=colors.HexColor("#17151B"), spaceAfter=3),
        "eyebrow": ParagraphStyle("EraEyebrow", parent=base["BodyText"], fontName="ERAUnicode", fontSize=7.8, leading=10, textColor=colors.HexColor("#9222A6"), spaceAfter=4),
        "lead": ParagraphStyle("EraLead", parent=base["BodyText"], fontName="ERAUnicode", fontSize=10.4, leading=14, textColor=colors.HexColor("#625C67"), spaceAfter=5),
        "section": ParagraphStyle("EraSection", parent=base["Heading2"], fontName="ERAUnicode", fontSize=12, leading=15, textColor=colors.HexColor("#E32731"), spaceBefore=9, spaceAfter=5),
        "body": ParagraphStyle("EraBody", parent=base["BodyText"], fontName="ERAUnicode", fontSize=9.2, leading=13.3, textColor=colors.HexColor("#272329"), spaceAfter=5),
        "small": ParagraphStyle("EraSmall", parent=base["BodyText"], fontName="ERAUnicode", fontSize=7.5, leading=10.2, textColor=colors.HexColor("#706A74")),
        "letter": ParagraphStyle("EraLetter", parent=base["BodyText"], fontName="ERAUnicode", fontSize=10.2, leading=16, textColor=colors.HexColor("#272329"), spaceAfter=8),
    }


def _header(styles, title: str, subtitle: str):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

    if not LOGO_PATH.exists():
        raise RuntimeError("ERA logo asset is unavailable")
    logo = Image(str(LOGO_PATH), width=30 * mm, height=30 * mm)
    copy = [
        Paragraph("ОБЪЕДИНЕНИЕ ЛИДЕРОВ И КУЛЬТУРНЫХ ИНИЦИАТИВ", styles["eyebrow"]),
        Paragraph(escape(title), styles["name"]),
        Paragraph(escape(subtitle), styles["lead"]),
    ]
    table = Table([[logo, copy]], colWidths=[36 * mm, 128 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LINEBELOW", (0, 0), (-1, -1), 1.1, colors.HexColor("#E32731")),
    ]))
    return [table, Spacer(1, 4 * mm)]


def _signature_block(styles, *, resume_note: bool):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

    note = (
        "Подписи и печать подтверждают только сведения с отметкой «Подтверждено ЭРА». "
        "Записи «Добавлено участником» включены в резюме по заявлению владельца портфолио."
        if resume_note
        else "Место для подписей уполномоченных лиц и печати организации."
    )
    table = Table(
        [
            ["Председатель", "________________________", "Багдасарян Д.С."],
            ["Заместитель председателя", "________________________", "Карапетян Е.А."],
            ["М.П.", "________________________", ""],
        ],
        colWidths=[49 * mm, 55 * mm, 61 * mm],
    )
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "ERAUnicode"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#2A262D")),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return KeepTogether([Spacer(1, 8 * mm), Paragraph(escape(note), styles["small"]), Spacer(1, 6 * mm), table])


def _user_item_html(item: CareerPortfolioItem) -> str:
    meta = [value for value in (item.organization, item.issued_at.strftime("%d.%m.%Y") if item.issued_at else None) if value]
    verified = item.status == "verified"
    label = "✓ Подтверждено ЭРА" if verified else "Добавлено участником"
    color = "#9222A6" if verified else "#77717B"
    description = escape(item.description or "")
    return (
        f"<b>{escape(item.title)}</b>{(' · ' + escape(' · '.join(meta))) if meta else ''}<br/>"
        f"<font color='{color}'>{escape(label)}</font>"
        f"{('<br/>' + description) if description else ''}"
    )


def _era_entry_html(item: PortfolioEntry) -> str:
    meta = " · ".join(part for part in (item.date_label, item.status) if part)
    description = item.description or item.category
    return (
        f"<b>{escape(item.title)}</b>{(' · ' + escape(meta)) if meta else ''}<br/>"
        "<font color='#9222A6'>✓ Подтверждено ЭРА</font>"
        f"{('<br/>' + escape(description)) if description else ''}"
    )


def _era_sections(portfolio: PortfolioData) -> dict[str, list[PortfolioEntry]]:
    return {
        "project": [item for item in portfolio.projects if item.status in {"Одобрен", "В работе", "Завершён", "вклад подтверждён"}],
        "event": [item for item in portfolio.events if item.status == "Посетил"],
        "task": [item for item in portfolio.tasks if item.status in {"Выполнена", "approved", "completed", "подтверждено"}],
        "leadership": portfolio.leadership,
        "certificate": portfolio.certificates,
        "achievement": portfolio.badges,
        "volunteer": [item for item in portfolio.volunteer if item.status in {"Выполнена", "approved", "completed", "подтверждено"}],
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
    styles = _document_styles()
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=14 * mm, bottomMargin=14 * mm, title=f"Резюме — {_full_name(user)}", author="ЭРА")
    story = _header(styles, _full_name(user), f"Резюме · {PURPOSE_LABELS.get(purpose, PURPOSE_LABELS['universal'])}")

    headline = (career_profile.headline or user.occupation or portfolio.participation_status or "").strip()
    contacts = " · ".join(value for value in (user.city or "", user.email or "") if value)
    if headline:
        story.append(Paragraph(escape(headline), styles["lead"]))
    if contacts:
        story.append(Paragraph(escape(contacts), styles["small"]))
    about = (career_profile.about or user.experience or "").strip()
    if about:
        story.extend([Paragraph("О себе", styles["section"]), Paragraph(escape(about), styles["body"])])
    skills = [str(value).strip() for value in (user.skills or []) if str(value).strip()][:8]
    if skills:
        story.extend([Paragraph("Ключевые компетенции", styles["section"]), Paragraph(escape(" · ".join(skills)), styles["body"])])

    grouped: dict[str, list[CareerPortfolioItem]] = {}
    for item in items:
        if item.include_in_resume and item.status != "pending":
            grouped.setdefault(item.item_type, []).append(item)
    era = _era_sections(portfolio)
    seen: set[str] = set()
    for item_type in PURPOSE_ORDER.get(purpose, PURPOSE_ORDER["universal"]):
        own = grouped.get(item_type, [])
        system_items = era.get(item_type, [])
        if not own and not system_items:
            continue
        seen.add(item_type)
        story.append(Paragraph(TYPE_LABELS.get(item_type, item_type.title()), styles["section"]))
        for item in system_items:
            story.append(Paragraph(_era_entry_html(item), styles["body"]))
        for item in own:
            story.append(Paragraph(_user_item_html(item), styles["body"]))
    for item_type, own in grouped.items():
        if item_type in seen:
            continue
        story.append(Paragraph(TYPE_LABELS.get(item_type, item_type.title()), styles["section"]))
        for item in own:
            story.append(Paragraph(_user_item_html(item), styles["body"]))

    languages = career_profile.languages or []
    language_text = " · ".join(
        f"{str(item.get('name', '')).strip()}{(' — ' + str(item.get('level', '')).strip()) if str(item.get('level', '')).strip() else ''}"
        for item in languages
        if str(item.get("name", "")).strip()
    )
    if language_text:
        story.extend([Paragraph("Языки", styles["section"]), Paragraph(escape(language_text), styles["body"])])

    metrics = [
        ("Мероприятия", len(era["event"])),
        ("Проекты / вклад", len(era["project"])),
        ("Задачи", len(era["task"])),
        ("Лидерские роли", len(era["leadership"])),
    ]
    metrics = [(label, value) for label, value in metrics if value]
    if metrics:
        story.append(Paragraph("Подтверждённая активность в ЭРА", styles["section"]))
        table = Table([[label, str(value)] for label, value in metrics], colWidths=[92 * mm, 24 * mm], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "ERAUnicode"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.2),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAF6FA")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E7DDE8")),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#EFE7F0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.extend([table, Spacer(1, 2 * mm)])

    story.append(_signature_block(styles, resume_note=True))
    doc.build(story)
    return stream.getvalue()


def _verification_qr(url: str):
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing

    qr = QrCodeWidget(url)
    bounds = qr.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    size = 76
    drawing = Drawing(size, size, transform=[size / width, 0, 0, size / height, 0, 0])
    drawing.add(qr)
    return drawing


def build_official_recommendation(user: User, request: RecommendationRequest, *, verification_url: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    if request.status != "approved" or not request.document_number:
        raise ValueError("recommendation_not_approved")
    _register_font()
    styles = _document_styles()
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm, topMargin=14 * mm, bottomMargin=14 * mm, title=f"Рекомендательное письмо — {_full_name(user)}", author="ЭРА")
    story = _header(styles, "Рекомендательное письмо", _full_name(user))
    issue_date = request.approved_at.date() if request.approved_at else date.today()
    meta = Table([
        ["Документ", request.document_number],
        ["Дата", issue_date.strftime("%d.%m.%Y")],
        ["Назначение", PURPOSE_LABELS.get(request.purpose, PURPOSE_LABELS["universal"])],
    ], colWidths=[36 * mm, 110 * mm])
    meta.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "ERAUnicode"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.3),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#9222A6")),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([meta, Spacer(1, 6 * mm)])
    text = (request.final_text or request.draft_text).strip()
    paragraphs = [part.strip() for part in text.split("\n") if part.strip()] or [text]
    for paragraph in paragraphs:
        story.append(Paragraph(escape(paragraph), styles["letter"]))

    verify = Table([[
        _verification_qr(verification_url),
        [
            Paragraph("Проверка документа", styles["section"]),
            Paragraph("QR подтверждает номер, дату выдачи и организацию. Личные материалы портфолио публично не раскрываются.", styles["small"]),
            Paragraph(f"ID: {escape(request.document_number)}", styles["small"]),
        ],
    ]], colWidths=[31 * mm, 110 * mm])
    verify.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAF6FA")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E7DDE8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([Spacer(1, 4 * mm), verify, _signature_block(styles, resume_note=False)])
    doc.build(story)
    return stream.getvalue()
