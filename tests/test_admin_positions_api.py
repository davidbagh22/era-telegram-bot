from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.services.position_management_service import AppointmentResult, PositionError


def _admin(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1, telegram_id=555, role="admin", is_blocked=False, is_archived=False, permission_grants=[]
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _office(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1,
        title="Куратор",
        description="d",
        is_active=True,
        is_public=True,
        permission_template=[],
        application_enabled=False,
        application_deadline=None,
        requirements=None,
        default_term_days=None,
        probation_days=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _application(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=10,
        office_id=1,
        user_id=2,
        status="submitted",
        motivation="m",
        plan=None,
        availability=None,
        submitted_at=None,
        reviewed_by=None,
        reviewed_at=None,
        review_note=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _summary():
    return SimpleNamespace(
        completed_projects=1,
        tasks_completed_on_time=2,
        tasks_completed_total=2,
        on_time_rate=100.0,
        events_attended=3,
        past_offices=0,
    )


def _build_app(user, session: SimpleNamespace) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_current_user] = lambda: user

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
    app.dependency_overrides[get_bot] = lambda: None
    return app


class AdminPositionsApiTests(unittest.TestCase):
    def test_list_office_applications(self) -> None:
        application = _application()
        office = _office()
        user = SimpleNamespace(id=2, first_name="A", last_name=None)
        session = SimpleNamespace(get=AsyncMock(side_effect=[office, user]))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.position_management_service.list_applications_for_office",
                new=AsyncMock(return_value=[application]),
            ),
            patch(
                "app.api.v1.admin.position_management_service.candidate_summary",
                new=AsyncMock(return_value=_summary()),
            ),
        ):
            response = client.get("/api/v1/admin/offices/1/applications")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["candidate_summary"]["completed_projects"], 1)

    def test_decide_application_success(self) -> None:
        application = _application()
        session = SimpleNamespace(get=AsyncMock(side_effect=[application, _office(), SimpleNamespace(id=2, first_name="A", last_name=None)]))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.position_management_service.review_application",
                new=AsyncMock(return_value=application),
            ),
            patch(
                "app.api.v1.admin.position_management_service.candidate_summary",
                new=AsyncMock(return_value=_summary()),
            ),
        ):
            response = client.post(
                "/api/v1/admin/position-applications/10/decision",
                json={"status": "approved", "note": "ok"},
            )
        self.assertEqual(response.status_code, 200)

    def test_decide_application_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/position-applications/999/decision", json={"status": "approved"}
        )
        self.assertEqual(response.status_code, 404)

    def test_appoint_from_application_success(self) -> None:
        application = _application(status="approved")
        office = _office()
        assignment = SimpleNamespace(
            id=5,
            office_id=1,
            user_id=2,
            appointment_type="regular",
            starts_at=date.today(),
            ends_at=None,
            probation_ends_at=None,
        )
        session = SimpleNamespace(get=AsyncMock(side_effect=[application, office]))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.position_management_service.appoint_from_application",
            new=AsyncMock(return_value=AppointmentResult(assignment=assignment, conflict_warnings=[])),
        ):
            response = client.post("/api/v1/admin/position-applications/10/appoint", json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["assignment_id"], 5)
        self.assertEqual(response.json()["conflict_warnings"], [])

    def test_appoint_from_application_conflict_warning_surfaced(self) -> None:
        application = _application(status="approved")
        office = _office()
        assignment = SimpleNamespace(
            id=5,
            office_id=1,
            user_id=2,
            appointment_type="regular",
            starts_at=date.today(),
            ends_at=None,
            probation_ends_at=None,
        )
        session = SimpleNamespace(get=AsyncMock(side_effect=[application, office]))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.position_management_service.appoint_from_application",
            new=AsyncMock(
                return_value=AppointmentResult(
                    assignment=assignment, conflict_warnings=["У пользователя уже 3 роли."]
                )
            ),
        ):
            response = client.post("/api/v1/admin/position-applications/10/appoint", json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["conflict_warnings"]), 1)

    def test_appoint_from_application_already_appointed(self) -> None:
        application = _application(status="appointed")
        office = _office()
        session = SimpleNamespace(get=AsyncMock(side_effect=[application, office]))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.position_management_service.appoint_from_application",
            new=AsyncMock(side_effect=PositionError("already_appointed")),
        ):
            response = client.post("/api/v1/admin/position-applications/10/appoint", json={})
        self.assertEqual(response.status_code, 422)

    def test_end_appointment(self) -> None:
        assignment = SimpleNamespace(id=5, office_id=1, is_active=True)
        office = _office()
        session = SimpleNamespace(get=AsyncMock(side_effect=[assignment, office]))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.position_management_service.end_appointment", new=AsyncMock()
            ),
            patch(
                "app.api.v1.admin.office_management_service.list_assignments",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.post(
                "/api/v1/admin/appointments/5/end", json={"reason": "term ended"}
            )
        self.assertEqual(response.status_code, 200)

    def test_extend_appointment(self) -> None:
        assignment = SimpleNamespace(id=5, office_id=1)
        office = _office()
        session = SimpleNamespace(get=AsyncMock(side_effect=[assignment, office]))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.position_management_service.extend_appointment", new=AsyncMock()
            ),
            patch(
                "app.api.v1.admin.office_management_service.list_assignments",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.post(
                "/api/v1/admin/appointments/5/extend", json={"ends_at": "2026-12-31"}
            )
        self.assertEqual(response.status_code, 200)

    def test_extend_appointment_invalid_date(self) -> None:
        assignment = SimpleNamespace(id=5, office_id=1)
        office = _office()
        session = SimpleNamespace(get=AsyncMock(side_effect=[assignment, office]))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/appointments/5/extend", json={"ends_at": "not-a-date"})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
