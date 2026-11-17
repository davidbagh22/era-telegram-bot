from __future__ import annotations

from datetime import date
from html import escape
from io import BytesIO
from pathlib import Path

from app.database.career_models import CareerPortfolioItem, CareerProfile, RecommendationRequest
from app.database.models import User
from app.services.portfolio_service import PortfolioData, PortfolioEntry

_ASSETS = Path(__file__).resolve().parents[1] / "assets"
_BRAND = _ASSETS / "era_logo_brand.jpg"
LOGO_PATH = _BRAND if _BRAND.exists() else _ASSETS / "era_logo.jpg"

# Visual TZ: docs/TZ_PORTFOLIO_VISUAL_2026_11_18.md
INK = "#0B1F1C"
MUTED = "#5B6B67"
HERO = "#0F3D38"
ACCENT = "#1A7A6D"
SOFT = "#E7F3F0"
RULE = "#C5D5D1"
PAPER = "#FFFFFF"

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
    "event": "Участие в мероприятиях",
    "achievement": "Достижения",
    "award": "Награды",
    "certificate": "Сертификаты участия",
    "course": "Курсы",
    "publication": "Публикации",
    "speech": "Выступления",
    "volunteer": "Волонтёрство",
    "task": "Задачи и миссии",
    "leadership": "Лидерские роли",
    "other": "Дополнительно",
}
PURPOSE_ORDER = {
    "work": [
        "event", "certificate", "work", "internship", "project", "leadership",
        "achievement", "education", "task", "course", "volunteer", "publication", "speech", "other",
    ],
    "internship": [
        "event", "certificate", "education", "project", "internship", "achievement",
        "leadership", "task", "course", "volunteer", "work", "other",
    ],
    "university": [
        "event", "certificate", "education", "achievement", "project", "leadership",
        "volunteer", "task", "course", "publication", "speech", "work", "other",
    ],
    "grant": [
        "event", "certificate", "achievement", "award", "project", "leadership",
        "volunteer", "education", "publication", "speech", "work", "other",
    ],
    "volunteer": [
        "event", "certificate", "volunteer", "project", "achievement", "leadership",
        "education", "task", "course", "work", "other",
    ],
    "universal": [
        "event", "certificate", "project", "leadership", "achievement", "award",
        "work", "education", "task", "volunteer", "internship", "course", "publication", "speech", "other",
    ],
}


def _full_name(user: User) -> str:
    return " ".join(part for part in (user.first_name, user.last_name) if part).strip() or "Участник ЭРА"


def _font_paths() -> tuple[Path, Path]:
    pairs = [
        (
            Path("/usr/share/fonts/truetype/macos/Inter-Regular.ttf"),
            Path("/usr/share/fonts/truetype/macos/Inter-Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
    ]
    for regular, bold in pairs:
        if regular.exists() and bold.exists():
            return regular, bold
    raise RuntimeError("Unicode font for ERA documents is unavailable")


def _register_font() -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    names = set(pdfmetrics.getRegisteredFontNames())
    regular, bold = _font_paths()
    if "ERASans" not in names:
        pdfmetrics.registerFont(TTFont("ERASans", str(regular)))
    if "ERASans-Bold" not in names:
        pdfmetrics.registerFont(TTFont("ERASans-Bold", str(bold)))
    # Legacy alias used by certificate / executive PDFs.
    if "ERAUnicode" not in names:
        pdfmetrics.registerFont(TTFont("ERAUnicode", str(regular)))
    try:
        from reportlab.pdfbase.pdfmetrics import registerFontFamily

        registerFontFamily("ERASans", normal="ERASans", bold="ERASans-Bold")
    except Exception:  # noqa: BLE001
        pass


def _document_styles():
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    return {
        "hero_brand": ParagraphStyle(
            "EraHeroBrand", parent=base["BodyText"], fontName="ERASans-Bold",
            fontSize=8, leading=10, textColor=colors.HexColor("#A8D5CE"), spaceAfter=2,
        ),
        "hero_name": ParagraphStyle(
            "EraHeroName", parent=base["Title"], fontName="ERASans-Bold",
            fontSize=24, leading=28, textColor=colors.white, spaceAfter=2,
        ),
        "hero_sub": ParagraphStyle(
            "EraHeroSub", parent=base["BodyText"], fontName="ERASans",
            fontSize=10, leading=13, textColor=colors.HexColor("#D5EBE6"), spaceAfter=0,
        ),
        "rail_title": ParagraphStyle(
            "EraRailTitle", parent=base["BodyText"], fontName="ERASans-Bold",
            fontSize=8.2, leading=10, textColor=colors.HexColor(ACCENT),
            spaceBefore=0, spaceAfter=4,
        ),
        "rail_body": ParagraphStyle(
            "EraRailBody", parent=base["BodyText"], fontName="ERASans",
            fontSize=8.4, leading=11.5, textColor=colors.HexColor(INK), spaceAfter=3,
        ),
        "rail_muted": ParagraphStyle(
            "EraRailMuted", parent=base["BodyText"], fontName="ERASans",
            fontSize=7.6, leading=10, textColor=colors.HexColor(MUTED), spaceAfter=2,
        ),
        "section": ParagraphStyle(
            "EraSection", parent=base["Heading2"], fontName="ERASans-Bold",
            fontSize=11, leading=13, textColor=colors.HexColor(HERO),
            spaceBefore=2, spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "EraBody", parent=base["BodyText"], fontName="ERASans",
            fontSize=9.2, leading=13.2, textColor=colors.HexColor(INK), spaceAfter=4,
        ),
        "entry_title": ParagraphStyle(
            "EraEntryTitle", parent=base["BodyText"], fontName="ERASans-Bold",
            fontSize=9.2, leading=12, textColor=colors.HexColor(INK), spaceAfter=0,
        ),
        "entry_meta": ParagraphStyle(
            "EraEntryMeta", parent=base["BodyText"], fontName="ERASans",
            fontSize=7.8, leading=10.5, textColor=colors.HexColor(MUTED), spaceAfter=0,
        ),
        "small": ParagraphStyle(
            "EraSmall", parent=base["BodyText"], fontName="ERASans",
            fontSize=7.2, leading=9.5, textColor=colors.HexColor(MUTED),
        ),
        "letter": ParagraphStyle(
            "EraLetter", parent=base["BodyText"], fontName="ERASans",
            fontSize=10.4, leading=16.2, textColor=colors.HexColor(INK), spaceAfter=8,
        ),
        "letter_name": ParagraphStyle(
            "EraLetterName", parent=base["Title"], fontName="ERASans-Bold",
            fontSize=18, leading=22, textColor=colors.HexColor(INK), spaceAfter=2,
        ),
        "brand": ParagraphStyle(
            "EraBrand", parent=base["BodyText"], fontName="ERASans-Bold",
            fontSize=8.5, leading=11, textColor=colors.HexColor(ACCENT), spaceAfter=2,
        ),
        "lead": ParagraphStyle(
            "EraLead", parent=base["BodyText"], fontName="ERASans",
            fontSize=10, leading=13, textColor=colors.HexColor(MUTED), spaceAfter=4,
        ),
    }


def _meaningful_text(value: str | None, *, min_chars: int = 24) -> str | None:
    text = (value or "").strip()
    if len(text) < min_chars:
        return None
    return text


def _dedupe_short(value: str | None, *others: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    lowered = text.casefold()
    for other in others:
        if other and lowered == other.strip().casefold():
            return None
    if len(text) < 12:
        return None
    return text


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


def _user_item_bits(item: CareerPortfolioItem) -> tuple[str, str, str]:
    meta = [value for value in (item.organization, item.issued_at.strftime("%d.%m.%Y") if item.issued_at else None) if value]
    verified = item.status == "verified"
    label = "✓ Подтверждено ЭРА" if verified else "Добавлено участником"
    return item.title, " · ".join(meta + [label]), item.description or ""


def _era_entry_bits(item: PortfolioEntry) -> tuple[str, str, str]:
    meta = " · ".join(part for part in (item.date_label, item.status, "✓ Подтверждено ЭРА") if part)
    return item.title, meta, item.description or item.category or ""


def _fit_canvas_text(canvas, text: str, *, font: str, max_size: float, min_size: float, max_width: float) -> tuple[str, float]:
    """Shrink font (then ellipsize) so the string fits the hero band width."""
    size = max_size
    while size >= min_size:
        if canvas.stringWidth(text, font, size) <= max_width:
            return text, size
        size -= 0.5
    clipped = text
    while clipped and canvas.stringWidth(clipped + "…", font, min_size) > max_width:
        clipped = clipped[:-1]
    return (clipped + "…") if clipped else text[:1], min_size


def _draw_hero(canvas, doc, *, title: str, subtitle: str, brand_line: str) -> None:
    from reportlab.lib.units import mm

    width, height = doc.pagesize
    band = 46 * mm
    side = 14 * mm
    canvas.saveState()
    canvas.setFillColorRGB(0x0F / 255, 0x3D / 255, 0x38 / 255)
    canvas.rect(0, height - band, width, band, fill=1, stroke=0)
    canvas.setFillColorRGB(0x1A / 255, 0x7A / 255, 0x6D / 255)
    canvas.rect(0, height - band - 2.2 * mm, width, 2.2 * mm, fill=1, stroke=0)
    if LOGO_PATH.exists():
        size = 22 * mm
        canvas.drawImage(
            str(LOGO_PATH),
            16 * mm,
            height - band + (band - size) / 2,
            width=size,
            height=size,
            preserveAspectRatio=True,
            mask="auto",
        )
    canvas.setFillColorRGB(0xA8 / 255, 0xD5 / 255, 0xCE / 255)
    canvas.setFont("ERASans-Bold", 8)
    text_x = 44 * mm
    max_text_w = width - text_x - side
    brand, brand_size = _fit_canvas_text(
        canvas, brand_line, font="ERASans-Bold", max_size=8, min_size=6, max_width=max_text_w
    )
    canvas.setFont("ERASans-Bold", brand_size)
    canvas.drawString(text_x, height - 14 * mm, brand)
    canvas.setFillColorRGB(1, 1, 1)
    fitted_title, title_size = _fit_canvas_text(
        canvas, title, font="ERASans-Bold", max_size=22, min_size=12, max_width=max_text_w
    )
    canvas.setFont("ERASans-Bold", title_size)
    canvas.drawString(text_x, height - 24 * mm, fitted_title)
    canvas.setFillColorRGB(0xD5 / 255, 0xEB / 255, 0xE6 / 255)
    fitted_sub, sub_size = _fit_canvas_text(
        canvas, subtitle, font="ERASans", max_size=9.5, min_size=7, max_width=max_text_w
    )
    canvas.setFont("ERASans", sub_size)
    canvas.drawString(text_x, height - 31 * mm, fitted_sub)
    canvas.restoreState()


def _skill_chips(styles, skills: list[str]):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle

    # One skill per soft strip for Cyrillic wrapping reliability.
    blocks = []
    for skill in skills[:12]:
        table = Table([[Paragraph(escape(skill), styles["rail_body"])]], colWidths=[52 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(SOFT)),
            ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor(RULE)),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        blocks.append(table)
    return blocks


def _metric_card(styles, label: str, value: int):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle

    table = Table(
        [
            [Paragraph(f"<b>{value}</b>", styles["rail_body"])],
            [Paragraph(escape(label), styles["rail_muted"])],
        ],
        colWidths=[52 * mm],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(SOFT)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(RULE)),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (0, 0), 6),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 5),
    ]))
    return table


def _entry_flowables(styles, title: str, meta: str, description: str, *, content_width_mm: float = 110) -> list:
    """Accent card flowables. Long descriptions stay outside tables so ReportLab can split them."""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

    accent_w = 2.2 * mm
    body_w = content_width_mm * mm
    header_bits = [Paragraph(escape(title), styles["entry_title"])]
    if meta:
        header_bits.append(Paragraph(escape(meta), styles["entry_meta"]))
    header = Table([["", header_bits]], colWidths=[accent_w, body_w])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(ACCENT)),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#F7FBFA")),
        ("BOX", (1, 0), (1, 0), 0.3, colors.HexColor(RULE)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 6),
        ("RIGHTPADDING", (1, 0), (1, 0), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    text = (description or "").strip()
    if len(text) < 12:
        return [KeepTogether([header, Spacer(1, 1.5 * mm)])]
    if len(text) > 900:
        text = text[:897].rstrip() + "…"
    body_style = ParagraphStyle(
        "EraEntryBody",
        parent=styles["body"],
        leftIndent=accent_w + 6,
        spaceBefore=1,
        spaceAfter=4,
    )
    body = Paragraph(escape(text), body_style)
    # Short cards stay together; long bodies split as a free Paragraph after the header.
    if len(text) < 280:
        return [KeepTogether([header, body, Spacer(1, 1.5 * mm)])]
    return [header, body, Spacer(1, 1.5 * mm)]


def _draw_resume_footer(canvas, doc, *, resume_note: bool = True) -> None:
    """Pin signatures to the physical bottom so sparse pages still look finished."""
    from reportlab.lib.units import mm

    width, _height = doc.pagesize
    side = 14 * mm
    y0 = 12 * mm
    note = (
        "Отметкой «Подтверждено ЭРА» отмечены записи, проверенные организацией. "
        "Остальные сведения добавлены владельцем портфолио."
        if resume_note
        else "Место для собственноручных подписей уполномоченных лиц и печати организации."
    )
    canvas.saveState()
    canvas.setStrokeColorRGB(0x1A / 255, 0x7A / 255, 0x6D / 255)
    canvas.setLineWidth(0.9)
    canvas.line(side, y0 + 28 * mm, width - side, y0 + 28 * mm)
    canvas.setFillColorRGB(0x5B / 255, 0x6B / 255, 0x67 / 255)
    canvas.setFont("ERASans", 7)
    # Two short lines so the disclaimer is never clipped.
    if resume_note:
        canvas.drawString(side, y0 + 23.5 * mm, "Отметкой «Подтверждено ЭРА» отмечены записи, проверенные организацией.")
        canvas.drawString(side, y0 + 20 * mm, "Остальные сведения добавлены владельцем портфолио.")
    else:
        canvas.drawString(side, y0 + 22 * mm, note[:110])
    canvas.setFillColorRGB(0x0B / 255, 0x1F / 255, 0x1C / 255)
    canvas.setFont("ERASans", 8)
    rows = [
        ("Председатель", "Багдасарян Д.С."),
        ("Заместитель председателя", "Карапетян Е.А."),
        ("М.П.", ""),
    ]
    for idx, (label, name) in enumerate(rows):
        y = y0 + 13 * mm - idx * 6.5 * mm
        canvas.drawString(side, y, label)
        canvas.setStrokeColorRGB(0xC5 / 255, 0xD5 / 255, 0xD1 / 255)
        canvas.setLineWidth(0.6)
        canvas.line(side + 52 * mm, y - 1, side + 110 * mm, y - 1)
        if name:
            canvas.drawString(side + 114 * mm, y, name)
    canvas.restoreState()


def _signature_footer(styles, *, resume_note: bool):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

    note = (
        "Отметкой «Подтверждено ЭРА» отмечены записи, проверенные организацией. "
        "Остальные сведения добавлены владельцем портфолио."
        if resume_note
        else "Место для собственноручных подписей уполномоченных лиц и печати организации."
    )
    table = Table(
        [
            ["Председатель", "________________________", "Багдасарян Д.С."],
            ["Заместитель председателя", "________________________", "Карапетян Е.А."],
            ["М.П.", "________________________", ""],
        ],
        colWidths=[52 * mm, 55 * mm, 55 * mm],
    )
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "ERASans"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(INK)),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEABOVE", (0, 0), (-1, 0), 0.7, colors.HexColor(ACCENT)),
    ]))
    return KeepTogether([Spacer(1, 4 * mm), Paragraph(escape(note), styles["small"]), Spacer(1, 3 * mm), table])


def build_career_resume(
    user: User,
    career_profile: CareerProfile,
    portfolio: PortfolioData,
    items: list[CareerPortfolioItem],
    *,
    purpose: str,
) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Frame,
        NextPageTemplate,
        PageTemplate,
        Paragraph,
        BaseDocTemplate,
        FrameBreak,
        Spacer,
    )

    _register_font()
    styles = _document_styles()
    stream = BytesIO()

    name = _full_name(user)
    headline = (career_profile.headline or user.occupation or portfolio.participation_status or "").strip()
    city = (user.city or "").strip()
    purpose_label = PURPOSE_LABELS.get(purpose, PURPOSE_LABELS["universal"])
    hero_sub = " · ".join(part for part in (headline, city, purpose_label) if part)

    about_raw = (career_profile.about or user.experience or "").strip()
    about = _meaningful_text(_dedupe_short(about_raw, headline, user.occupation), min_chars=20)
    skills = [str(value).strip() for value in (user.skills or []) if str(value).strip()][:12]
    languages = career_profile.languages or []
    language_lines = [
        f"{str(item.get('name', '')).strip()}{(' — ' + str(item.get('level', '')).strip()) if str(item.get('level', '')).strip() else ''}"
        for item in languages
        if str(item.get("name", "")).strip()
    ]

    grouped: dict[str, list[CareerPortfolioItem]] = {}
    for item in items:
        if item.include_in_resume and item.status not in {"pending", "revoked"}:
            grouped.setdefault(item.item_type, []).append(item)
    era = _era_sections(portfolio)

    metrics = [
        ("Мероприятия", len(era["event"])),
        ("Сертификаты", len(era["certificate"])),
        ("Проекты", len(era["project"])),
        ("Роли", len(era["leadership"])),
    ]
    metrics = [(label, value) for label, value in metrics if value > 0]

    page_width, page_height = A4
    top_margin = 52 * mm
    side = 14 * mm
    # Reserve space for canvas-pinned signature footer
    bottom = 36 * mm
    gap = 6 * mm
    left_w = 58 * mm
    right_w = page_width - side * 2 - left_w - gap
    is_sparse = not any(True for key in PURPOSE_ORDER["universal"] if era.get(key) or grouped.get(key)) and not about

    def _on_page(canvas, doc):
        _draw_hero(
            canvas,
            doc,
            title=name,
            subtitle=hero_sub or "Портфолио участника ЭРА",
            brand_line="ЭРА · ОБЪЕДИНЕНИЕ ЛИДЕРОВ И КУЛЬТУРНЫХ ИНИЦИАТИВ",
        )
        _draw_resume_footer(canvas, doc, resume_note=True)

    doc = BaseDocTemplate(
        stream,
        pagesize=A4,
        title=f"Портфолио — {name}",
        author="ЭРА",
        leftMargin=side,
        rightMargin=side,
        topMargin=top_margin,
        bottomMargin=bottom,
    )
    left_frame = Frame(side, bottom, left_w, page_height - top_margin - bottom, id="left", showBoundary=0)
    right_frame = Frame(
        side + left_w + gap,
        bottom,
        right_w,
        page_height - top_margin - bottom,
        id="right",
        showBoundary=0,
    )
    # Overflow pages use a full-width frame so wide activity cards are never forced into the 58 mm rail.
    cont_frame = Frame(
        side,
        bottom,
        page_width - side * 2,
        page_height - top_margin - bottom,
        id="continuation",
        showBoundary=0,
    )
    doc.addPageTemplates([
        PageTemplate(id="main", frames=[left_frame, right_frame], onPage=_on_page),
        PageTemplate(id="continuation", frames=[cont_frame], onPage=_on_page),
    ])
    left_story: list = [
        Paragraph("ПРОФИЛЬ", styles["rail_title"]),
        Paragraph(escape(headline or "Участник ЭРА"), styles["rail_body"]),
    ]
    if city:
        left_story.append(Paragraph(escape(city), styles["rail_muted"]))
    if skills:
        left_story.extend([Spacer(1, 3 * mm), Paragraph("НАВЫКИ", styles["rail_title"]), *_skill_chips(styles, skills)])
    if language_lines:
        left_story.extend([Spacer(1, 3 * mm), Paragraph("ЯЗЫКИ", styles["rail_title"])])
        for line in language_lines:
            left_story.append(Paragraph(escape(line), styles["rail_body"]))
    rail_metrics = metrics or ([("Мероприятия", 0), ("Сертификаты", 0), ("Проекты", 0), ("Роли", 0)] if is_sparse else [])
    if rail_metrics:
        left_story.extend([Spacer(1, 3 * mm), Paragraph("АКТИВНОСТЬ ЭРА", styles["rail_title"])])
        for label, value in rail_metrics:
            left_story.extend([_metric_card(styles, label, value), Spacer(1, 2 * mm)])

    right_story: list = []
    if about:
        right_story.extend([Paragraph("О себе", styles["section"]), Paragraph(escape(about), styles["body"]), Spacer(1, 2 * mm)])

    right_w_mm = right_w / mm - 2.2
    seen: set[str] = set()
    for item_type in PURPOSE_ORDER.get(purpose, PURPOSE_ORDER["universal"]):
        own = grouped.get(item_type, [])
        system_items = era.get(item_type, [])
        if not own and not system_items:
            continue
        seen.add(item_type)
        right_story.append(Paragraph(TYPE_LABELS.get(item_type, item_type.title()), styles["section"]))
        for item in system_items:
            title, meta, description = _era_entry_bits(item)
            right_story.extend(_entry_flowables(styles, title, meta, description, content_width_mm=right_w_mm))
        for item in own:
            title, meta, description = _user_item_bits(item)
            right_story.extend(_entry_flowables(styles, title, meta, description, content_width_mm=right_w_mm))
        right_story.append(Spacer(1, 1.5 * mm))

    for item_type, own in grouped.items():
        if item_type in seen:
            continue
        right_story.append(Paragraph(TYPE_LABELS.get(item_type, item_type.title()), styles["section"]))
        for item in own:
            title, meta, description = _user_item_bits(item)
            right_story.extend(_entry_flowables(styles, title, meta, description, content_width_mm=right_w_mm))

    if is_sparse:
        from reportlab.lib import colors
        from reportlab.platypus import Table, TableStyle

        empty_copy = Paragraph(
            "<b>Подтверждённая активность</b><br/><br/>"
            "Это официальный каркас портфолио ЭРА. Здесь появятся участия в мероприятиях, "
            "сертификаты, проекты и лидерские роли — по мере подтверждённой активности.<br/><br/>"
            "<b>Что заполнить перед следующей выгрузкой</b><br/>"
            "• 3–5 предложений о себе<br/>"
            "• ключевые навыки<br/>"
            "• языки и уровень",
            styles["body"],
        )
        empty = Table([[empty_copy]], colWidths=[right_w])
        empty.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(SOFT)),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(ACCENT)),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        right_story.extend([empty, Spacer(1, 4 * mm), Paragraph("Структура портфолио", styles["section"])])
        for ghost_title, ghost_hint in (
            ("Участие в мероприятиях", "Появится после посещения и подтверждения"),
            ("Сертификаты участия", "Выдаются автоматически после одобрения"),
            ("Проекты", "Одобренные вклады в проекты ЭРА"),
            ("Лидерские роли", "Назначения и ответственность в объединении"),
        ):
            right_story.extend(
                _entry_flowables(styles, ghost_title, "Ожидается", ghost_hint, content_width_mm=right_w_mm)
            )

    # After the first-page right column fills, continue on a full-width template (not the sidebar frame).
    story = left_story + [FrameBreak(), NextPageTemplate("continuation")] + right_story
    doc.build(story)
    return stream.getvalue()


def _verification_qr(url: str):
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing

    qr = QrCodeWidget(url)
    bounds = qr.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    size = 70
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
    name = _full_name(user)

    def _on_page(canvas, doc):
        _draw_hero(
            canvas,
            doc,
            title="Рекомендательное письмо",
            subtitle=name,
            brand_line="ЭРА · ОФИЦИАЛЬНЫЙ ДОКУМЕНТ",
        )

    doc = SimpleDocTemplate(
        stream,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=52 * mm,
        bottomMargin=16 * mm,
        title=f"Рекомендательное письмо — {name}",
        author="ЭРА",
    )
    issue_date = request.approved_at.date() if request.approved_at else date.today()
    meta = Table([
        ["Документ", request.document_number],
        ["Дата", issue_date.strftime("%d.%m.%Y")],
        ["Назначение", PURPOSE_LABELS.get(request.purpose, PURPOSE_LABELS["universal"])],
    ], colWidths=[36 * mm, 120 * mm])
    meta.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "ERASans"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor(ACCENT)),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor(INK)),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(SOFT)),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(RULE)),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story = [meta, Spacer(1, 7 * mm)]
    text = (request.final_text or request.draft_text).strip()
    paragraphs = [part.strip() for part in text.split("\n") if part.strip()] or [text]
    for paragraph in paragraphs:
        story.append(Paragraph(escape(paragraph), styles["letter"]))

    verify = Table([[
        _verification_qr(verification_url),
        [
            Paragraph("Проверка документа", styles["section"]),
            Paragraph(
                "QR подтверждает номер, дату выдачи и организацию. "
                "Личные материалы портфолио публично не раскрываются.",
                styles["small"],
            ),
            Paragraph(f"ID: {escape(request.document_number)}", styles["small"]),
        ],
    ]], colWidths=[28 * mm, 120 * mm])
    verify.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(SOFT)),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(RULE)),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([Spacer(1, 4 * mm), verify, _signature_footer(styles, resume_note=False)])
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return stream.getvalue()
