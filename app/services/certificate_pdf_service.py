from datetime import date
from html import escape
from io import BytesIO

from app.services.career_pdf_service import _register_font


def build_certificate_pdf(snapshot, *, number=None, issued_at=None, revoked=False):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, KeepInFrame

    _register_font()
    output = BytesIO()
    width, height = landscape(A4)
    document = SimpleDocTemplate(output, pagesize=(width, height), topMargin=33*mm,
                                 bottomMargin=25*mm, leftMargin=35*mm, rightMargin=35*mm,
                                 title="Сертификат ЭРА", author="ЭРА")
    def style(size, color="#242424", gap=8):
        return ParagraphStyle(f"Cert{size}{gap}", fontName="ERAUnicode", fontSize=size,
                              leading=size*1.4, alignment=TA_CENTER, textColor=colors.HexColor(color), spaceAfter=gap)
    def paragraph(text, size, color="#242424", gap=8):
        return Paragraph(escape(str(text)), style(size, color, gap))
    event_date = date.fromisoformat(snapshot["event_date"]).strftime("%d.%m.%Y")
    story = [paragraph("ЭРА", 18, gap=4), paragraph("СЕРТИФИКАТ", 30, gap=13),
             paragraph("Подтверждает участие", 12, "#707070"),
             paragraph(snapshot["full_name"], 23, gap=10), paragraph(snapshot["event_title"], 16),
             paragraph(event_date, 12), Spacer(1, 4*mm), paragraph(f"Подписант: {snapshot['signatory']}", 11),
             paragraph(f"{number or 'ПРЕДПРОСМОТР - номер не присвоен'}" +
                       (f" • Выдан {issued_at:%d.%m.%Y}" if issued_at else ""), 9, "#707070", gap=4),
             paragraph(f"Шаблон: {snapshot['template_version']}", 8, "#707070")]
    def page(canvas, doc):
        canvas.setStrokeColor(colors.HexColor("#B9B9B9"))
        canvas.rect(14*mm, 14*mm, width-28*mm, height-28*mm)
        if revoked or not number:
            canvas.saveState()
            canvas.setFont("ERAUnicode", 11)
            canvas.setFillColor(colors.HexColor("#B12222"))
            canvas.drawCentredString(width/2, height-23*mm,
                                     "ОТОЗВАН - документ недействителен" if revoked else "ПРЕДПРОСМОТР - документ не выдан")
            canvas.restoreState()
    document.build([KeepInFrame(width-70*mm-12, height-58*mm-12, story, mode="shrink")],
                   onFirstPage=page, onLaterPages=page)
    return output.getvalue()
