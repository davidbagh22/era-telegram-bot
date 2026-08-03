from __future__ import annotations

TASK_SUBMIT_PREFIX = "task_submit_"


def task_submit_deep_link(bot_username: str, task_id: int) -> str:
    """Mini App -> Bot handoff for task submission (section 15 of the
    platform brief). Uploads and conversational flows stay bot-only, so the
    Mini App only ever links into the existing FSM here rather than
    re-implementing file upload handling itself.

    Not cryptographically signed: the bot re-checks
    task_service.can_submit() before entering the FSM (see
    app/handlers/start.py), which is the same authorization check already
    enforced for the equivalent in-bot "📤 Отправить результат" button — an
    unsigned task id cannot grant access beyond what that check allows.
    """
    return f"https://t.me/{bot_username}?start={TASK_SUBMIT_PREFIX}{task_id}"


def parse_task_submit_payload(payload: str) -> int | None:
    if not payload.startswith(TASK_SUBMIT_PREFIX):
        return None
    try:
        return int(payload[len(TASK_SUBMIT_PREFIX) :])
    except ValueError:
        return None
