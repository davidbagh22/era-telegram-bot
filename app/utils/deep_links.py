from __future__ import annotations

from urllib.parse import urlencode

TASK_SUBMIT_PREFIX = "task_submit_"
ACTIVITY_SUBMIT_PREFIX = "activity_submit_"


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


def activity_submit_deep_link(bot_username: str, activity_id: int) -> str:
    """Mini App -> Bot handoff for Event Activity proof submission — same
    rationale as task_submit_deep_link() above: uploads (photo/file) and
    the free-text/link prompts stay a Bot-only FSM. Not cryptographically
    signed for the same reason: the bot re-checks the participant's
    active registration before entering the FSM."""
    return f"https://t.me/{bot_username}?start={ACTIVITY_SUBMIT_PREFIX}{activity_id}"


def parse_activity_submit_payload(payload: str) -> int | None:
    if not payload.startswith(ACTIVITY_SUBMIT_PREFIX):
        return None
    try:
        return int(payload[len(ACTIVITY_SUBMIT_PREFIX) :])
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


def miniapp_projects_url(miniapp_url: str) -> str:
    """Deep-links straight into the participant Projects tab."""
    return miniapp_path_url(miniapp_url, "projects")


def miniapp_events_url(miniapp_url: str) -> str:
    """Deep-links straight into the Mini App's Activity screen, Events tab
    — used by the bot's "📅 Ближайшее" quick-access button (PR 36's Bot/Mini
    App role split) instead of the old bot-side "📅 Афиша" inline menu."""
    return miniapp_path_url(miniapp_url, "events")


def miniapp_tasks_url(miniapp_url: str) -> str:
    """Deep-links straight into the Mini App's Activity screen, Tasks tab —
    used by the bot's "✅ Мои задачи" quick-access button."""
    return miniapp_path_url(miniapp_url, "tasks")


def miniapp_opportunities_url(miniapp_url: str) -> str:
    """Deep-links straight into the Mini App's Opportunities screen — used
    by the bot's "⭐ Возможности" quick-access button."""
    return miniapp_path_url(miniapp_url, "opportunities")


def miniapp_community_url(miniapp_url: str) -> str:
    """Deep-links straight into the participant Community tab."""
    return miniapp_path_url(miniapp_url, "community")


def miniapp_task_url(miniapp_url: str, task_id: int) -> str:
    """Deep-links to a single task's detail inside the Activity screen's
    Tasks tab — used by task-assigned/decided notifications (PR 40)."""
    return miniapp_path_url(miniapp_url, f"tasks/{task_id}")


def miniapp_event_url(miniapp_url: str, event_id: int) -> str:
    """Deep-links to a single event's detail inside the Activity screen's
    Events tab — used by event-related notifications (PR 40)."""
    return miniapp_path_url(miniapp_url, f"events/{event_id}")


def miniapp_opportunity_url(miniapp_url: str, opportunity_id: int) -> str:
    """Deep-links to a single opportunity's detail in the Opportunities
    screen — used by opportunity-related notifications (PR 40)."""
    return miniapp_path_url(miniapp_url, f"opportunities/{opportunity_id}")


def miniapp_profile_url(miniapp_url: str) -> str:
    """Deep-links straight into the Mini App's Profile screen (personal
    data, points balance, leaderboard access, portfolio) — used by the
    bot's /profile, /data, and /points compatibility redirects (2026-08
    master spec section 25: these used to open a bot-native menu tree,
    now they just hand off to the one real Profile screen instead)."""
    return miniapp_path_url(miniapp_url, "profile")
