from __future__ import annotations

from urllib.parse import urlencode

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


def miniapp_path_url(
    miniapp_url: str, path: str, params: dict[str, str | int] | None = None
) -> str:
    """Build an exact Mini App object URL without requiring server routes for
    every client-side screen. The hash path keeps `/app/` reload-safe while
    giving the frontend a stable deep-link contract to parse later."""
    if not miniapp_url:
        return ""
    normalized_path = path.strip("/")
    query = f"?{urlencode(params)}" if params else ""
    return f"{miniapp_url.rstrip('/')}/#/{normalized_path}{query}"


def miniapp_project_url(miniapp_url: str, project_id: int) -> str:
    return miniapp_path_url(miniapp_url, f"projects/{project_id}")


def miniapp_project_application_url(
    miniapp_url: str, project_id: int, application_id: int
) -> str:
    return miniapp_path_url(
        miniapp_url,
        f"projects/{project_id}/team/applications/{application_id}",
    )


def miniapp_admin_project_url(miniapp_url: str, project_id: int) -> str:
    return miniapp_path_url(miniapp_url, f"admin/projects/{project_id}")
