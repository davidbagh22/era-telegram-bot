from datetime import date
from html import escape
from io import BytesIO
from pathlib import Path

from app.services.career_pdf_service import LOGO_PATH, _register_font

SEAL_PATH = Path(__file__).resolve().parents[1] / "assets" / "era_seal_signature.png"
BRAND_LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "era_logo_brand.jpg"


def build_certificate_pdf(snapshot, *, number=None, issued_at=None, revoked=False):
    """Landscape participation certificate with brand mark + baked seal/signature."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, KeepInFrame, Paragraph, SimpleDocTemplate, Spacer

    _register_font()
    output = BytesIO()
    width, height = landscape(A4)
    document = SimpleDocTemplate(
        output,
        pagesize=(width, height),
        topMargin=28 * mm,
        bottomMargin=22 * mm,
        leftMargin=28 * mm,
        rightMargin=28 * mm,
        title="Сертификат участника ЭРА",
        author="ЭРА",
    )

    def style(size, color="#1A1520", gap=6, leading=None):
        return ParagraphStyle(
            f"Cert{size}{color}{gap}",
            fontName="ERAUnicode",
            fontSize=size,
            leading=leading or size * 1.35,
            alignment=TA_CENTER,
            textColor=colors.HexColor(color),
            spaceAfter=gap,
        )

    def paragraph(text, size, color="#1A1520", gap=6):
        return Paragraph(escape(str(text)), style(size, color, gap))

    event_date = date.fromisoformat(snapshot["event_date"]).strftime("%d.%m.%Y")
    logo_file = BRAND_LOGO_PATH if BRAND_LOGO_PATH.exists() else LOGO_PATH
    story = []
    if logo_file.exists():
        story.append(Image(str(logo_file), width=42 * mm, height=14 * mm, kind="proportional"))
        story.append(Spacer(1, 4 * mm))
    story.extend(
        [
            paragraph("ОБЪЕДИНЕНИЕ ЛИДЕРОВ И КУЛЬТУРНЫХ ИНИЦИАТИВ", 8, "#9222A6", gap=3),
            paragraph("СЕРТИФИКАТ УЧАСТНИКА", 26, "#E32731", gap=10),
            paragraph("Настоящим подтверждается, что", 11, "#625C67", gap=4),
            paragraph(snapshot["full_name"], 22, gap=8),
            paragraph("принял(а) участие в мероприятии", 11, "#625C67", gap=4),
            paragraph(snapshot["event_title"], 15, gap=6),
            paragraph(event_date, 12, "#625C67", gap=8),
        ]
    )
    if SEAL_PATH.exists():
        story.append(Image(str(SEAL_PATH), width=48 * mm, height=40 * mm, kind="proportional"))
        story.append(Spacer(1, 2 * mm))
    else:
        story.append(paragraph(f"Подписант: {snapshot['signatory']}", 10, "#625C67"))
    story.append(
        paragraph(
            f"{number or 'ПРЕДПРОСМОТР — номер не присвоен'}"
            + (f" · Выдан {issued_at:%d.%m.%Y}" if issued_at else ""),
            9,
            "#8A8490",
            gap=2,
        )
    )

    def page(canvas, doc):
        canvas.setStrokeColor(colors.HexColor("#E32731"))
        canvas.setLineWidth(1.4)
        canvas.rect(12 * mm, 12 * mm, width - 24 * mm, height - 24 * mm)
        canvas.setStrokeColor(colors.HexColor("#9222A6"))
        canvas.setLineWidth(0.5)
        canvas.rect(14 * mm, 14 * mm, width - 28 * mm, height - 28 * mm)
        if revoked or not number:
            canvas.saveState()
            canvas.setFont("ERAUnicode", 11)
            canvas.setFillColor(colors.HexColor("#B12222"))
            canvas.drawCentredString(
                width / 2,
                height - 20 * mm,
                "ОТОЗВАН — документ недействителен" if revoked else "ПРЕДПРОСМОТР — документ не выдан",
            )
            canvas.restoreState()

    document.build(
        [KeepInFrame(width - 56 * mm, height - 50 * mm, story, mode="shrink")],
        onFirstPage=page,
        onLaterPages=page,
    )
    return output.getvalue()
