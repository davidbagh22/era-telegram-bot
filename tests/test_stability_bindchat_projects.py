from datetime import date, time

from sqlalchemy import create_engine, inspect

from app.database import Base
from app.database.models import Project
from app.handlers.chat_binding import CHAT_KEYS
from app.handlers.participant.project_event_stability import _project_date, _project_time
from app.services.event_service import PUBLIC_EVENT_STATUSES, REGISTRATION_ALLOWED_STATUSES
from app.utils.constants import EventStatus


def test_bind_command_covers_all_operational_chats() -> None:
    assert CHAT_KEYS["general"][0] == "general_chat_id"
    assert CHAT_KEYS["internal"][0] == "internal_department_chat_id"
    assert CHAT_KEYS["external"][0] == "external_department_chat_id"
    assert CHAT_KEYS["leaders"][0] == "leaders_chat_id"
    assert CHAT_KEYS["channel"][0] == "era_channel_id"


def test_project_event_uses_structured_date_and_time_first() -> None:
    project = Project(
        author_id=1,
        title="Проект",
        short_description="Описание",
        form_data={"proposed_date": "01.01.2020", "proposed_time": "09:00"},
    )
    project.proposed_date = date(2026, 9, 15)
    project.proposed_time = time(18, 30)

    assert _project_date(project, project.form_data) == date(2026, 9, 15)
    assert _project_time(project, project.form_data) == time(18, 30)


def test_project_event_falls_back_to_form_data() -> None:
    project = Project(
        author_id=1,
        title="Проект",
        short_description="Описание",
        form_data={"proposed_date": "15.09.2026", "proposed_time": "18:30"},
    )

    assert _project_date(project, project.form_data) == date(2026, 9, 15)
    assert _project_time(project, project.form_data) == time(18, 30)


def test_event_schema_keeps_project_link_and_public_statuses() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    event_columns = {column["name"] for column in inspect(engine).get_columns("events")}

    assert "project_id" in event_columns
    assert EventStatus.APPROVED in PUBLIC_EVENT_STATUSES
    assert EventStatus.REGISTRATION_OPEN in REGISTRATION_ALLOWED_STATUSES
