from io import BytesIO
from pathlib import Path


def build_era_resume(user, items, stats: dict) -> bytes:
    """Build a compact branded PDF resume with a Unicode font."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
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
    name = f"{user.first_name} {user.last_name or ''}".strip()
    story = [
        Paragraph("ЭРА", title),
        Paragraph("ПОРТФОЛИО УЧАСТНИКА", title),
        Spacer(1, 6 * mm),
        Paragraph(name, heading),
        Paragraph(
            f"Город: {user.city or '—'}<br/>"
            f"Telegram: @{user.username or '—'}<br/>"
            f"Email: {user.email or '—'}",
            body,
        ),
        Spacer(1, 5 * mm),
    ]
    metrics = Table(
        [
            ["Баллы", "Мероприятия", "Проекты", "Задания"],
            [
                str(stats.get("points", 0)),
                str(stats.get("events", 0)),
                str(stats.get("projects", 0)),
                str(stats.get("tasks", 0)),
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
    story.extend([metrics, Paragraph("Достижения и опыт", heading)])
    if items:
        for item in items:
            details = item.description or item.item_type
            story.append(Paragraph(f"• <b>{item.title}</b><br/>{details}", body))
            story.append(Spacer(1, 2 * mm))
    else:
        story.append(Paragraph("Подтверждённых достижений пока нет", body))
    story.extend(
        [
            Spacer(1, 8 * mm),
            Paragraph(
                "Документ сформирован ботом общественной организации «ЭРА»",
                body,
            ),
        ]
    )
    document.build(story)
    return stream.getvalue()
