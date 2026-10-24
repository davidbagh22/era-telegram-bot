from datetime import date
from types import SimpleNamespace as NS
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, Response

from app.api.v1 import admin_executive_export as api


class AdminReportDeliveryTests(IsolatedAsyncioTestCase):
    def payload(self, **kwargs):
        return api.ReportSendIn(period="custom", start_date=date(2026, 10, 1),
                                end_date=date(2026, 10, 24), request_key="request-1234567890", **kwargs)

    async def test_only_current_admin_receives_the_shared_report(self):
        admin = NS(id=1, telegram_id=100)
        session = AsyncMock()
        session.scalar.return_value = None
        settings, bot = NS(timezone="Asia/Yerevan"), NS()
        for format in ["pdf", "xlsx"]:
            with self.subTest(format=format), \
                 patch.object(api, "export_executive_report", AsyncMock(return_value=Response(b"report"))) as builder, \
                 patch.object(api, "safe_send_once", AsyncMock(return_value=NS(sent=True, duplicate=False))) as sender:
                result = await api.send_executive_report(self.payload(format=format), admin, session, settings, bot)
                self.assertTrue(result["sent"])
                self.assertEqual(builder.call_args.args[:4], (format, "custom", date(2026, 10, 1), date(2026, 10, 24)))
                self.assertEqual(sender.call_args.args[2], admin.telegram_id)
                self.assertEqual(sender.call_args.kwargs["document"].data, b"report")

    async def test_confirmed_replay_does_not_build_or_send_again(self):
        session = AsyncMock()
        session.scalar.return_value = NS(status="sent", chat_id=100)
        with patch.object(api, "export_executive_report", AsyncMock()) as builder, \
             patch.object(api, "safe_send_once", AsyncMock()) as sender:
            result = await api.send_executive_report(self.payload(), NS(id=1, telegram_id=100), session, NS(timezone="Asia/Yerevan"), NS())
        self.assertEqual(result, {"sent": True, "duplicate": True})
        builder.assert_not_awaited()
        sender.assert_not_awaited()

    async def test_uncertain_or_other_recipient_is_not_replayed(self):
        for receipt in [NS(status="uncertain", chat_id=100), NS(status="pending", chat_id=100), NS(status="sent", chat_id=200)]:
            session = AsyncMock()
            session.scalar.return_value = receipt
            with patch.object(api, "safe_send_once", AsyncMock()) as sender:
                with self.assertRaises(HTTPException) as caught:
                    await api.send_executive_report(self.payload(), NS(id=1, telegram_id=100), session, NS(timezone="Asia/Yerevan"), NS())
                self.assertEqual(caught.exception.status_code, 409)
                sender.assert_not_awaited()

    async def test_delivery_failure_is_not_success(self):
        session = AsyncMock()
        session.scalar.return_value = None
        with patch.object(api, "export_executive_report", AsyncMock(return_value=Response(b"report"))), \
             patch.object(api, "safe_send_once", AsyncMock(return_value=NS(sent=False))):
            with self.assertRaises(HTTPException) as caught:
                await api.send_executive_report(self.payload(), NS(id=1, telegram_id=100), session, NS(timezone="Asia/Yerevan"), NS())
        self.assertEqual(caught.exception.status_code, 502)

    def test_client_cannot_supply_another_recipient(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            self.payload(chat_id=200)


class AdminReportHTTPAuthorizationTests(TestCase):
    def test_non_admin_cannot_trigger_a_document_delivery(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.config import Settings
        app = FastAPI()
        app.include_router(api.router)
        app.dependency_overrides[api.get_current_user] = lambda: NS(
            id=9, telegram_id=90, role="participant", is_blocked=False, is_archived=False, permission_grants=[])
        app.dependency_overrides[api.get_settings] = lambda: Settings(bot_token="1234567890:test-token")
        app.dependency_overrides[api.get_session] = lambda: AsyncMock()
        app.dependency_overrides[api.get_bot] = lambda: NS()
        with patch.object(api, "export_executive_report", AsyncMock()) as builder:
            result = TestClient(app).post("/admin/analytics/executive-report/send", json={"request_key": "request-1234567890"})
        self.assertEqual(result.status_code, 403)
        builder.assert_not_awaited()
