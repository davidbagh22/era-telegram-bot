from datetime import date
from io import BytesIO
from types import SimpleNamespace as NS
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from pypdf import PdfReader

from app.services.executive_pdf_service import build_executive_pdf


def fixture():
    wb = Workbook()
    ws = wb.active
    ws.title = '01 · Сводка'
    ws.append(['ЭРА'])
    ws.append(['Период'])
    ws.append([])
    ws.append(['Показатель', 'Значение', 'Описание', 'Источник'])
    ws.append(['Текущий состав', 66, 'Одобренные участники', 'User'])
    ws = wb.create_sheet('02 · Люди')
    ws.append(['Участник', 'Статус'])
    ws.append(['Имя <script> & текст', 'Одобрено'])
    ws = wb.create_sheet('03 · Пустой раздел')
    ws.append(['Запись', 'Статус'])
    ws.append(['Данных за выбранный период нет', ''])
    ws = wb.create_sheet('04 · Длинные записи')
    ws.append(['Запись', 'Описание'])
    ws.append(['Подробности', 'Очень длинный текст <без разметки> ' * 700])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def report():
    return build_executive_pdf(fixture(), period_label='01.10.2026–21.10.2026',
        health=NS(risks=['Сроки требуют внимания'], metrics=[], period_label='30 дней'),
        efficiency=NS(recommendations=[], period_label='7 дней'))


class ExecutivePDFTests(TestCase):
    def test_unicode_escaping_all_sections_and_long_pagination(self):
        content = report()
        self.assertTrue(content.startswith(b'%PDF-'))
        pdf = PdfReader(BytesIO(content))
        text = '\n'.join(page.extract_text() for page in pdf.pages)
        for expected in ['Текущий состав', '66', 'Приоритеты руководителя',
                         'Имя <script> & текст', 'Данных за выбранный период нет',
                         '01.10.2026', 'Сроки требуют внимания', 'Очень длинный текст']:
            self.assertIn(expected, text)
        self.assertGreater(len(pdf.pages), 4)
        self.assertTrue(all('Для внутреннего использования' in page.extract_text() for page in pdf.pages))


class ExecutivePDFRouteTests(TestCase):
    def setUp(self):
        from app.api.v1 import admin_executive_export as api
        self.api = api
        app = FastAPI()
        app.include_router(api.router)
        app.dependency_overrides[api.get_session] = lambda: object()
        app.dependency_overrides[api.get_settings] = lambda: NS(timezone='Asia/Yerevan')
        app.dependency_overrides[api.require_admin] = lambda: NS(id=1)
        self.app = app
        self.client = TestClient(app)

    def test_period_pdf_headers_and_shared_facts(self):
        api = self.api
        with patch.object(api, 'build_analytics_payload', AsyncMock(return_value=NS())), \
             patch.object(api, 'build_efficiency_snapshot', AsyncMock(return_value=NS())), \
             patch.object(api, 'build_extended_organization_health', AsyncMock(return_value=NS())), \
             patch.object(api, 'build_executive_workbook', AsyncMock(return_value=fixture())) as builder:
            response = self.client.get('/admin/analytics/executive-report.pdf?period=custom&start_date=2026-10-01&end_date=2026-10-21')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'application/pdf')
        self.assertEqual(response.headers['cache-control'], 'no-store, private')
        self.assertIn('20261001-20261021.pdf', response.headers['content-disposition'])
        self.assertEqual(builder.call_args.kwargs['start_date'], date(2026, 10, 1))

    def test_invalid_period_does_not_build_report(self):
        with patch.object(self.api, 'build_analytics_payload', AsyncMock()) as builder:
            response = self.client.get('/admin/analytics/executive-report.pdf?period=custom&start_date=2026-10-21&end_date=2026-10-01')
        self.assertEqual(response.status_code, 422)
        builder.assert_not_awaited()
        self.assertEqual(self.client.get('/admin/analytics/executive-report.exe').status_code, 422)


class ExecutivePDFAuthorizationTests(IsolatedAsyncioTestCase):
    async def test_category_access_does_not_allow_export(self):
        from fastapi import HTTPException
        from app.api.v1.admin_executive_export import require_admin
        with patch('app.api.v1.admin_executive_export.has_dashboard_access', return_value=False):
            with self.assertRaises(HTTPException) as denied:
                await require_admin(NS(telegram_id=7), NS())
        self.assertEqual(denied.exception.status_code, 403)
