from io import BytesIO
from pathlib import Path


def build_era_resume(user, items, stats: dict, photo_bytes: bytes | None = None) -> bytes:
    """Build a clean branded Russian PDF portfolio for an ERA participant."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        HRFlowable,
        Image,
        KeepTogether,
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
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title="Портфолио участника ЭРА",
        author="Общественная организация ЭРА",
    )
    styles = getSampleStyleSheet()
    brand = colors.HexColor("#7C27C9")
    accent = colors.HexColor("#EC2533")
    ink = colors.HexColor("#29242D")
    muted = colors.HexColor("#6B6270")
    pale = colors.HexColor("#F7F1FA")
    pale_red = colors.HexColor("#FDECEF")

    title = ParagraphStyle(
        "EraTitle",
        parent=styles["Title"],
        fontName="ERAUnicode",
        textColor=colors.white,
        alignment=TA_LEFT,
        fontSize=20,
        leading=24,
    )
    subtitle = ParagraphStyle(
        "EraSubtitle",
        parent=styles["BodyText"],
        fontName="ERAUnicode",
        textColor=colors.white,
        fontSize=9,
        leading=13,
    )
    name_style = ParagraphStyle(
        "EraName",
        parent=styles["Heading1"],
        fontName="ERAUnicode",
        textColor=ink,
        fontSize=18,
        leading=22,
        spaceAfter=4,
    )
    heading = ParagraphStyle(
        "EraHeading",
        parent=styles["Heading2"],
        fontName="ERAUnicode",
        textColor=brand,
        fontSize=13,
        leading=16,
        spaceBefore=8,
        spaceAfter=5,
    )
    body = ParagraphStyle(
        "EraBody",
        parent=styles["BodyText"],
        fontName="ERAUnicode",
        fontSize=9.5,
        leading=14,
        textColor=ink,
    )
    muted_body = ParagraphStyle(
        "EraMuted",
        parent=body,
        textColor=muted,
        fontSize=8.5,
    )

    header = Table(
        [[Paragraph("ЭРА", title), Paragraph("ПОРТФОЛИО УЧАСТНИКА<br/>Путь, опыт и достижения", subtitle)]],
        colWidths=[32 * mm, 140 * mm],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), brand),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 11),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
            ]
        )
    )

    name = f"{user.first_name} {user.last_name or ''}".strip()
    contact = (
        f"Город: {user.city or '—'}<br/>"
        f"Telegram: {'@' + user.username if user.username else '—'}<br/>"
        f"Почта: {user.email or '—'}<br/>"
        f"Телефон: {user.phone or '—'}"
    )
    departments = ", ".join(
        item.department.name
        for item in (getattr(user, "departments", None) or [])
        if getattr(item, "department", None)
    ) or "Пока не выбран"
    directions = ", ".join(
        item.direction.name
        for item in (getattr(user, "directions", None) or [])
        if getattr(item, "direction", None)
    ) or "Пока не выбрано"

    identity_content = [
        Paragraph(name, name_style),
        Paragraph(f"Роль в ЭРА: {getattr(user, 'role', 'участник')}", body),
        Spacer(1, 2 * mm),
        Paragraph(contact, muted_body),
    ]
    identity = [identity_content]
    if photo_bytes:
        try:
            image = Image(BytesIO(photo_bytes), width=34 * mm, height=34 * mm)
            image.hAlign = "RIGHT"
            identity = [identity_content, image]
        except Exception:
            identity = [identity_content]

    identity_table = Table([identity], colWidths=[136 * mm] + ([36 * mm] if len(identity) > 1 else []))
    identity_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), pale),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E4DCE7")),
            ]
        )
    )

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
        colWidths=[43 * mm] * 4,
    )
    metrics.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "ERAUnicode"),
                ("BACKGROUND", (0, 0), (-1, 0), pale_red),
                ("TEXTCOLOR", (0, 0), (-1, 0), accent),
                ("TEXTCOLOR", (0, 1), (-1, 1), ink),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("FONTSIZE", (0, 1), (-1, 1), 14),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E4DCE7")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E4DCE7")),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    story = [
        header,
        Spacer(1, 6 * mm),
        identity_table,
        Spacer(1, 5 * mm),
        metrics,
        Paragraph("Мой путь в ЭРА", heading),
        Paragraph(f"<b>Департаменты:</b> {departments}<br/><b>Направления:</b> {directions}", body),
    ]

    recommendations = [x for x in items if x.item_type == "recommendation_letter"]
    achievements = [
        x for x in items
        if x.item_type not in {"recommendation_letter", "profile_photo"}
    ]

    story.append(Paragraph("Достижения и опыт", heading))
    if achievements:
        for item in achievements:
            details = item.description or item.item_type
            date_text = f" · {item.issued_at:%d.%m.%Y}" if item.issued_at else ""
            story.append(
                KeepTogether(
                    [
                        Paragraph(f"<b>{item.title}</b>{date_text}", body),
                        Paragraph(details, muted_body),
                        Spacer(1, 2.5 * mm),
                    ]
                )
            )
    else:
        story.append(Paragraph("Подтверждённых достижений пока нет", muted_body))

    story.append(Paragraph("Рекомендации", heading))
    if recommendations:
        for item in recommendations:
            story.append(
                Paragraph(
                    f"<b>{item.title}</b><br/>{item.description or 'Рекомендательное письмо прикреплено в портфолио ЭРА'}",
                    body,
                )
            )
            story.append(Spacer(1, 2 * mm))
    else:
        story.append(Paragraph("Рекомендательных писем пока нет", muted_body))

    story.extend(
        [
            Spacer(1, 6 * mm),
            HRFlowable(width="100%", thickness=0.7, color=brand),
            Spacer(1, 2 * mm),
            Paragraph(
                "Документ сформирован ботом общественной организации «ЭРА». "
                "Подтверждающие файлы хранятся в личном портфолио участника",
                muted_body,
            ),
        ]
    )
    document.build(story)
    return stream.getvalue()
