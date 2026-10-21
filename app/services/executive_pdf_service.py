"""Readable executive PDF, using the exact workbook facts (no parallel formulas)."""
from __future__ import annotations

from datetime import date, datetime
from html import escape
from io import BytesIO

from openpyxl import load_workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepTogether, CondPageBreak, Table, TableStyle,
)

from app.services.career_pdf_service import _register_font


def build_executive_pdf(workbook: bytes, *, period_label: str, health, efficiency) -> bytes:
    _register_font()
    ink = colors.HexColor('#202032')
    muted = colors.HexColor('#656575')
    accent = colors.HexColor('#632CFF')
    styles = {
        key: ParagraphStyle(key, fontName='ERAUnicode', fontSize=size, leading=leading,
                            textColor=color, spaceAfter=after, splitLongWords=True)
        for key, size, leading, color, after in [
            ('title', 28, 34, ink, 16), ('heading', 18, 24, ink, 14),
            ('body', 10, 15, ink, 8), ('small', 8, 12, muted, 5),
            ('value', 24, 30, accent, 4), ('eyebrow', 9, 13, accent, 10),
        ]
    }
    styles['heading'].keepWithNext = True
    def p(value, style='body'):
        if value is None:
            value = '—'
        elif isinstance(value, (date, datetime)):
            value = value.strftime('%d.%m.%Y')
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), styles[style])

    output = BytesIO()
    from reportlab.graphics.shapes import Drawing, Rect

    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm,
                            topMargin=23*mm, bottomMargin=21*mm,
                            title='ЭРА · Аналитический отчёт', author='ЭРА')
    def page(canvas, document):
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(accent)
        canvas.setLineWidth(2)
        canvas.line(20*mm, height-15*mm, width-20*mm, height-15*mm)
        canvas.setFont('ERAUnicode', 8)
        canvas.setFillColor(muted)
        canvas.drawString(20*mm, height-11*mm, 'ЭРА / Аналитический отчёт')
        canvas.setFillColor(muted)
        canvas.drawString(20*mm, 12*mm, 'ЭРА · Для внутреннего использования')
        canvas.drawRightString(width-20*mm, 12*mm, str(document.page))
        canvas.restoreState()

    wb = load_workbook(BytesIO(workbook), read_only=True, data_only=False)
    story = [p('ЭРА / АНАЛИТИКА', 'eyebrow'), p('Организация\nв цифрах', 'title'),
             p(period_label, 'heading'),
             p('Главные результаты, зоны внимания и полный обзор разделов.', 'small')]
    # Large metric tiles instead of a spreadsheet pasted into a PDF.
    rows = list(wb.worksheets[0].values)[4:]
    tiles = []
    for row in rows:
        tiles.append([p(row[1], 'value'), p(row[0]), p(row[2], 'small')])
    for i in range(0, len(tiles), 2):
        pair = tiles[i:i+2]
        if len(pair) == 1:
            pair.append('')
        table = Table([pair], colWidths=[83*mm, 83*mm], hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F3F0FA')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        story.extend([table, Spacer(1, 3*mm)])
    story.extend([p('Как читать отчёт', 'heading'), p(
        'События, проекты и результаты отфильтрованы по выбранным датам. '
        'Состав организации — текущий срез. Эффективность и пульс имеют собственные '
        'окна расчёта; их нельзя интерпретировать как оценку выбранного периода.', 'small'),
        p(f'Период пульса: {getattr(health, "period_label", "текущее окно")}', 'small'),
        p(f'Период эффективности: {getattr(efficiency, "period_label", "текущее окно")}', 'small'),
        PageBreak(), p('Приоритеты руководителя', 'heading')])
    risks = getattr(health, 'risks', [])
    story.extend(p(risk) for risk in risks)
    recommendations = getattr(efficiency, 'recommendations', [])
    for item in recommendations:
        story.extend([p(item.title, 'eyebrow'), p(item.reason), p(item.action)])
    if not risks and not recommendations:
        story.append(p('В доступных данных нет отдельных сигналов или рекомендаций.'))
    if not getattr(health, 'pulse_suppressed', True):
        story.append(p('Пульс по направлениям', 'heading'))
        for item in getattr(health, 'vector_dimensions', []):
            delta = getattr(item, 'delta', None)
            change = ' · нет сравнения' if delta is None else f' · изменение {delta:+g}'
            story.append(p(f'{item.label}: {item.value}{change}'))
            bar = Drawing(460, 16)
            bar.add(Rect(0, 4, 460, 6, fillColor=colors.HexColor('#EDEAF4'), strokeColor=None))
            bar.add(Rect(0, 4, 460 * max(0, min(100, item.value)) / 100, 6,
                         fillColor=accent, strokeColor=None))
            story.append(bar)
    story.extend([p('Все показатели', 'heading')])
    for metric in getattr(health, 'metrics', []):
        story.append(KeepTogether([p(f'{metric.label} · {metric.display}'), p(metric.note, 'small')]))
    story.append(p('Подробные разделы', 'heading'))
    story.extend(p(sheet.title, 'small') for sheet in wb.worksheets[1:])
    for sheet in wb.worksheets[1:]:
        story.extend([Spacer(1, 6*mm), CondPageBreak(55*mm), p(sheet.title, 'heading')])
        iterator = iter(sheet.values)
        headers = next(iterator, ())
        for number, row in enumerate(iterator, 1):
            if not any(value is not None for value in row):
                continue
            # Paragraphs can split across pages even for unusually long user content.
            story.append(p(f'{number:02d} / {row[0] if row[0] is not None else "—"}', 'eyebrow'))
            for label, value in zip(headers[1:], row[1:]):
                if value is not None and value != '':
                    display = value.strftime('%d.%m.%Y') if isinstance(value, (date, datetime)) else value
                    story.append(p(f'{label}: {display}'))
            story.append(Spacer(1, 3*mm))
    wb.close()
    doc.build(story, onFirstPage=page, onLaterPages=page)
    return output.getvalue()
