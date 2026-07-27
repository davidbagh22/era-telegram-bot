from app.services.event_service import can_change_event_status
from app.utils.constants import EventStatus


def test_event_status_transitions_follow_lifecycle() -> None:
    assert can_change_event_status(
        EventStatus.PUBLISHED, EventStatus.REGISTRATION_OPEN
    )
    assert can_change_event_status(
        EventStatus.REGISTRATION_OPEN, EventStatus.REGISTRATION_CLOSED
    )
    assert can_change_event_status(
        EventStatus.REGISTRATION_OPEN, EventStatus.ACTIVE
    )
    assert can_change_event_status(
        EventStatus.REGISTRATION_CLOSED, EventStatus.ACTIVE
    )
    assert can_change_event_status(EventStatus.ACTIVE, EventStatus.COMPLETED)


def test_event_status_transitions_reject_direct_callback_jumps() -> None:
    assert not can_change_event_status(
        EventStatus.DRAFT, EventStatus.REGISTRATION_OPEN
    )
    assert not can_change_event_status(
        EventStatus.PENDING_APPROVAL, EventStatus.COMPLETED
    )
    assert not can_change_event_status(
        EventStatus.COMPLETED, EventStatus.REGISTRATION_OPEN
    )
    assert not can_change_event_status("not-a-status", EventStatus.ACTIVE)
