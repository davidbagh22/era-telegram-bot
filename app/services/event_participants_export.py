"""Shared participant list export for one event (XLSX and CSV).

Used by the admin export endpoints and by the automatic owner delivery, so the
file the owner receives is exactly what the admin screen would download.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from io import BytesIO, StringIO
from zoneinfo import ZoneInfo

from openpyxl import Workbook

from app.database.models import EventRegistration, User
from app.utils.constants import REGISTRATION_STATUS_LABELS

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXPORT_HEADERS = [
    "Имя",
    "Фамилия",
    "Номер телефона",
    "ФИО для регистрации",
    "Организация или вуз",
    "Статус",
    "Время регистрации",
]
ParticipantRow = tuple[EventRegistration, User]


def safe_export_name(value: str) -> str:
    """Neutralise spreadsheet formula injection and line breaks in a cell."""
    clean = value.replace("\r", " ").replace("\n", " ").strip()
    return "'" + clean if clean.startswith(("=", "+", "-", "@")) else clean


def status_label(status: str) -> str:
    return REGISTRATION_STATUS_LABELS.get(status, status)  # type: ignore[call-overload]


def format_registered_at(value: datetime | None, timezone_name: str) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = timezone.utc
    return value.astimezone(zone).strftime("%d.%m.%Y %H:%M")


def export_rows(rows: Iterable[ParticipantRow], timezone_name: str) -> list[list[str]]:
    result: list[list[str]] = []
    for registration, participant in rows:
        signup = getattr(registration, "signup", None) or {}
        result.append(
            [
                safe_export_name(participant.first_name or ""),
                safe_export_name(participant.last_name or ""),
                safe_export_name(signup.get("phone") or participant.phone or ""),
                safe_export_name(signup.get("full_name", "")),
                safe_export_name(signup.get("organization", "")),
                status_label(registration.status),
                format_registered_at(getattr(registration, "created_at", None), timezone_name),
            ]
        )
    return result


def build_participants_xlsx(rows: Sequence[ParticipantRow], timezone_name: str) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Участники"
    sheet.append(EXPORT_HEADERS)
    for line in export_rows(rows, timezone_name):
        sheet.append(line)
    sheet.freeze_panes = "A2"
    for column, width in zip("ABCDEFG", (24, 28, 22, 30, 30, 22, 20), strict=True):
        sheet.column_dimensions[column].width = width
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def build_participants_csv(rows: Sequence[ParticipantRow], timezone_name: str) -> str:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(EXPORT_HEADERS)
    writer.writerows(export_rows(rows, timezone_name))
    return "\ufeff" + output.getvalue()
