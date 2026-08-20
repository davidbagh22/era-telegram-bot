from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TASK_SUBMIT_PREFIX = "task_submit_"
ACTIVITY_SUBMIT_PREFIX = "activity_submit_"
ATTENDANCE_PREFIX = "att"
MINIAPP_ROUTE_PARAM = "eraPath"


def task_submit_deep_link(bot_username: str, task_id: int) -> str:
    """Mini App -> Bot handoff for task submission."""
    return f"https://t.me/{bot_username}?start={TASK_SUBMIT_PREFIX}{task_id}"


def parse_task_submit_payload(payload: str) -> int | None:
    if not payload.startswith(TASK_SUBMIT_PREFIX):
        return None
    try:
        return int(payload[len(TASK_SUBMIT_PREFIX) :])
    except ValueError:
        return None


def activity_submit_deep_link(bot_username: str, activity_id: int) -> str:
    """Mini App's Event Activities screen hands off here for proof submission."""
    return f"https://t.me/{bot_username}?start={ACTIVITY_SUBMIT_PREFIX}{activity_id}"


def parse_activity_submit_payload(payload: str) -> int | None:
    if not payload.startswith(ACTIVITY_SUBMIT_PREFIX):
        return None
    try:
        return int(payload[len(ACTIVITY_SUBMIT_PREFIX) :])
    except ValueError:
        return None


def _attendance_signature(event_id: int, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        str(event_id).encode("ascii"),
        hashlib.sha256,
    ).digest()[:8]
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def attendance_payload(event_id: int, secret: str) -> str:
    """Short signed Telegram /start payload for event attendance.

    It carries no user data. The event id is authenticated with HMAC and the
    actual check-in is still authorized against the database and event time.
    """
    if event_id <= 0 or not secret:
        raise ValueError("invalid attendance token input")
    return f"{ATTENDANCE_PREFIX}_{event_id}_{_attendance_signature(event_id, secret)}"


def parse_attendance_payload(payload: str, secret: str) -> int | None:
    try:
        prefix, raw_event_id, signature = payload.split("_", 2)
        event_id = int(raw_event_id)
    except (ValueError, AttributeError):
        return None
    if prefix != ATTENDANCE_PREFIX or event_id <= 0 or not secret:
        return None
    expected = _attendance_signature(event_id, secret)
    return event_id if hmac.compare_digest(signature, expected) else None


def attendance_deep_link(bot_username: str, event_id: int, secret: str) -> str:
    username = bot_username.lstrip("@").strip()
    if not username:
        raise ValueError("bot username is required")
    return f"https://t.me/{username}?start={attendance_payload(event_id, secret)}"


def telegram_miniapp_start_url(bot_username: str, start_param: str) -> str:
    """Open the bot's Main Mini App from a group-safe ordinary URL.

    Telegram only permits WebAppInfo reply-keyboard buttons in private chats.
    `startapp` is therefore the direct route used by inline buttons in shared
    chats; the frontend consumes the parameter and routes inside the Mini App.
    """
    username = bot_username.lstrip("@").strip()
    start_param = start_param.strip()
    if not username or not start_param:
        return ""
    return f"https://t.me/{username}?{urlencode({'startapp': start_param})}"


def telegram_event_miniapp_url(bot_username: str, event_id: int) -> str:
    if event_id <= 0:
        return ""
    return telegram_miniapp_start_url(bot_username, f"event_{event_id}")


def telegram_profile_miniapp_url(bot_username: str) -> str:
    return telegram_miniapp_start_url(bot_username, "profile")


def miniapp_path_url(
    miniapp_url: str, path: str, params: dict[str, str | int] | None = None
) -> str:
    """Build a Telegram-safe Mini App deep link.

    Telegram's iOS WebView may open a WebAppInfo URL after dropping or
    normalising the fragment. Keep the destination in a normal query parameter;
    the frontend converts it to its internal hash route after boot.
    """
    if not miniapp_url:
        return ""
    normalized_path = path.strip("/")
    parts = urlsplit(miniapp_url)
    app_path = parts.path if parts.path.endswith("/") else f"{parts.path}/"
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[MINIAPP_ROUTE_PARAM] = normalized_path
    if params:
        query.update({key: str(value) for key, value in params.items()})
    return urlunsplit((parts.scheme, parts.netloc, app_path, urlencode(query), ""))


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
    return miniapp_path_url(miniapp_url, "projects")


def miniapp_events_url(miniapp_url: str) -> str:
    return miniapp_path_url(miniapp_url, "events")


def miniapp_tasks_url(miniapp_url: str) -> str:
    return miniapp_path_url(miniapp_url, "tasks")


def miniapp_opportunities_url(miniapp_url: str) -> str:
    return miniapp_path_url(miniapp_url, "opportunities")


def miniapp_community_url(miniapp_url: str) -> str:
    return miniapp_path_url(miniapp_url, "community")


def miniapp_task_url(miniapp_url: str, task_id: int) -> str:
    return miniapp_path_url(miniapp_url, f"tasks/{task_id}")


def miniapp_event_url(miniapp_url: str, event_id: int) -> str:
    return miniapp_path_url(miniapp_url, f"events/{event_id}")


def miniapp_opportunity_url(miniapp_url: str, opportunity_id: int) -> str:
    return miniapp_path_url(miniapp_url, f"opportunities/{opportunity_id}")


def miniapp_profile_url(miniapp_url: str) -> str:
    return miniapp_path_url(miniapp_url, "profile")


def miniapp_admin_url(miniapp_url: str) -> str:
    return miniapp_path_url(miniapp_url, "admin")


def miniapp_leader_url(miniapp_url: str) -> str:
    return miniapp_path_url(miniapp_url, "leader")
