from datetime import date, time
from types import SimpleNamespace

from app.services.activity_service import collapse_duplicate_geo_dictation
from app.utils.constants import RegistrationStatus


def event(event_id: int, title: str, *, marker: str = ""):
    return SimpleNamespace(
        id=event_id, title=title, event_date=date(2026, 11, 22),
        event_time=time(12), additional_info=marker,
    )


def test_22_nov_geography_dictation_is_one_public_card_without_deleting_data():
    original = event(77, "Международная просветительская акция «Географический диктант — 2026» 🌍")
    official = event(88, "Географический диктант — 2026",
                     marker="geo-dictation-2026-russian-house")
    other = event(89, "Семинар")
    rows = [(original, None), (official, None), (other, None)]
    collapsed = collapse_duplicate_geo_dictation(rows)
    assert [row[0].id for row in collapsed] == [88, 89]
    assert len(rows) == 3  # No database changes or registration transfers.


def test_prefer_actual_registration_and_keep_other_dates_and_sessions():
    original = event(77, "Географический диктант — 2026")
    official = event(88, "Географический диктант — 2026",
                     marker="geo-dictation-2026-russian-house")
    registered = SimpleNamespace(status=RegistrationStatus.REGISTERED)
    rows = [(original, registered), (official, None)]
    assert [e.id for e, _ in collapse_duplicate_geo_dictation(rows)] == [77]
    later = event(100, "Географический диктант — 2026")
    later.event_date = date(2026, 11, 29)
    assert len(collapse_duplicate_geo_dictation([(official, None), (later, None)])) == 2


def test_does_not_hide_different_event_at_same_time():
    geography = event(88, "Географический диктант — 2026")
    other = event(89, "Конференция культурных инициатив")
    assert len(collapse_duplicate_geo_dictation([(geography, None), (other, None)])) == 2
