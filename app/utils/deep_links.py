from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TASK_SUBMIT_PREFIX = "task_submit_"
ACTIVITY_SUBMIT_PREFIX = "activity_submit_"
MINIAPP_ROUTE_PARAM = "eraPath"


def task_submit_deep_link(bot_username: str, task_id: int) -> str:
    """Mini App -> Bot handoff for task submission.

    Uploads and conversational flows stay bot-only; authorization is rechecked
    in the bot before the FSM starts, so the task id itself does not grant
    access.
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
    """Mini App -> Bot handoff for Event Activity proof submission."""
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
    """Build a Telegram-safe Mini App deep link.

    Telegram's iOS WebView may open a WebAppInfo URL after dropping or
    normalising the fragment. The old contract stored the whole destination in
    ``#/...`` and therefore occasionally landed on Home. Keep the destination
    in a normal query parameter instead; the frontend converts it to its
    internal hash route after boot. Existing query parameters are preserved.
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
