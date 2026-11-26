"""#321 prep: structured 48-laws educational analyses with publish gated OFF.

Public Telegram delivery stays blocked unless BOTH
``settings.literature_48_laws_publish_enabled`` and the existing exact-day
series approval are true. Admin preview never posts to channel/chat.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from html import escape
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.content.literature_issues import LAW_TITLES
from app.services.book_club_service import (
    PROGRAM_START,
    publication_number,
    series_issue_delivery,
    series_issue_is_approved,
    yerevan_today,
)

ASSET_PATH = Path(__file__).resolve().parents[1] / "content" / "laws_48_analyses.json"
TARGET_COUNT = 48
SERIES_ID = "era-48-laws-educational-analyses"


@dataclass(frozen=True)
class Law48Analysis:
    law_number: int
    title: str
    case_study: str
    critical_view: str
    discussion_question: str
    summary: str = ""
    practical_task: str = ""
    audio_url: str | None = None
    content_complete: bool = True


REQUIRED_TEXT_FIELDS = (
    "title",
    "case_study",
    "critical_view",
    "discussion_question",
)


def publish_enabled(settings: Settings) -> bool:
    """Hard launch switch — default False so prep never auto-posts."""
    return bool(getattr(settings, "literature_48_laws_publish_enabled", False))


def topic_delivery_key(start_day: date, number: int) -> str:
    """Idempotent general-topic key (send_general_topic prefixes topic name)."""
    return f"issue:{start_day.isoformat()}:{number}"


def subscriber_delivery_key(start_day: date, number: int, user_id: int) -> str:
    return f"book-club:{start_day.isoformat()}:{number}:{user_id}"


def task_points_idempotency_key(user_id: int, number: int) -> str:
    from app.services.points_service import make_idempotency_key

    return make_idempotency_key("literature", "task", user_id, number)


@lru_cache(maxsize=1)
def _load_raw() -> dict:
    data = json.loads(ASSET_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise ValueError("laws_48_analyses.json: invalid root")
    return data


def reload_asset() -> dict:
    _load_raw.cache_clear()
    return _load_raw()


def content_progress() -> dict:
    """Completeness report: how many of 48 entries are ready for review."""
    data = _load_raw()
    entries = data["entries"]
    complete = [
        e for e in entries
        if isinstance(e, dict)
        and e.get("content_complete")
        and all(str(e.get(field) or "").strip() for field in REQUIRED_TEXT_FIELDS)
        and 1 <= int(e.get("law_number") or 0) <= TARGET_COUNT
    ]
    numbers = sorted({int(e["law_number"]) for e in complete})
    missing = [n for n in range(1, TARGET_COUNT + 1) if n not in numbers]
    audio_ready = sum(1 for e in complete if e.get("audio_url"))
    return {
        "series": data.get("series") or SERIES_ID,
        "schema_version": data.get("schema_version"),
        "target_count": int(data.get("target_count") or TARGET_COUNT),
        "complete_count": len(complete),
        "missing_law_numbers": missing,
        "audio_url_set_count": audio_ready,
        "audio_url_null_count": len(complete) - audio_ready,
        "publish_seed_enabled": bool(data.get("publish_enabled_default")),
        "todo_remaining_content": list(data.get("todo_remaining_content") or missing),
        "is_complete": len(complete) == TARGET_COUNT and not missing,
    }


def validate_store() -> None:
    data = _load_raw()
    entries = data["entries"]
    if len(entries) > TARGET_COUNT:
        raise ValueError("laws_48_analyses.json: more than 48 entries")
    seen: set[int] = set()
    for raw in entries:
        number = int(raw.get("law_number") or 0)
        if number in seen:
            raise ValueError(f"duplicate law_number {number}")
        seen.add(number)
        analysis = _entry_to_analysis(raw)
        if analysis.content_complete:
            _validate_complete(analysis)
        audio = raw.get("audio_url")
        if audio is not None and not isinstance(audio, str):
            raise ValueError(f"law {number}: audio_url must be string or null")
        if isinstance(audio, str) and not audio.startswith(("https://", "http://")):
            raise ValueError(f"law {number}: fabricated/non-http audio_url rejected")


def _entry_to_analysis(raw: dict) -> Law48Analysis:
    number = int(raw["law_number"])
    title = str(raw.get("title") or "").strip() or LAW_TITLES[number - 1]
    audio = raw.get("audio_url")
    return Law48Analysis(
        law_number=number,
        title=title,
        case_study=str(raw.get("case_study") or "").strip(),
        critical_view=str(raw.get("critical_view") or "").strip(),
        discussion_question=str(raw.get("discussion_question") or "").strip(),
        summary=str(raw.get("summary") or "").strip(),
        practical_task=str(raw.get("practical_task") or "").strip(),
        audio_url=audio.strip() if isinstance(audio, str) and audio.strip() else None,
        content_complete=bool(raw.get("content_complete", True)),
    )


def _validate_complete(analysis: Law48Analysis) -> None:
    if not 1 <= analysis.law_number <= TARGET_COUNT:
        raise ValueError("law_number must be 1..48")
    for field in REQUIRED_TEXT_FIELDS:
        if not getattr(analysis, field).strip():
            raise ValueError(f"incomplete analysis #{analysis.law_number}: {field}")


def get_analysis(number: int) -> Law48Analysis:
    if not 1 <= number <= TARGET_COUNT:
        raise ValueError("Unknown law number")
    for raw in _load_raw()["entries"]:
        if int(raw.get("law_number") or 0) == number:
            analysis = _entry_to_analysis(raw)
            if analysis.content_complete:
                _validate_complete(analysis)
            return analysis
    raise ValueError(f"No analysis for law {number}")


def list_analyses(*, complete_only: bool = False) -> tuple[Law48Analysis, ...]:
    items = []
    for raw in _load_raw()["entries"]:
        analysis = _entry_to_analysis(raw)
        if complete_only and not analysis.content_complete:
            continue
        if analysis.content_complete:
            _validate_complete(analysis)
        items.append(analysis)
    return tuple(sorted(items, key=lambda item: item.law_number))


def render_analysis(number: int) -> str:
    """HTML preview/body for one analysis. Does not send anywhere."""
    item = get_analysis(number)
    sections = [
        ("Кратко", item.summary),
        ("Кейс", item.case_study),
        ("Критический взгляд", item.critical_view),
        ("Вопрос для обсуждения", item.discussion_question),
        ("Практика", item.practical_task),
    ]
    body = "\n\n".join(
        f"<b>{label}</b>\n{escape(text)}" for label, text in sections if text.strip()
    )
    audio_line = ""
    if item.audio_url:
        audio_line = f"\n\n🎧 Аудио: {escape(item.audio_url)}"
    else:
        audio_line = "\n\n🎧 Аудио: не приложено (ссылка не подтверждена)."
    return (
        f"📚 ЭРА · «48 законов» · предпросмотр\n"
        f"<b>Закон {item.law_number}/48 · {escape(item.title)}</b>\n\n"
        f"{body}{audio_line}\n\n"
        f"<i>Подготовка #321 · публичная отправка выключена, пока "
        f"literature_48_laws_publish_enabled=false.</i>"
    )


async def is_issue_published(
    session: AsyncSession, number: int, *, start_day: date = PROGRAM_START
) -> bool:
    receipt = await series_issue_delivery(session, start_day, number)
    return bool(receipt and receipt.status in {"sent", "already_sent"})


async def next_unpublished_analysis(
    session: AsyncSession, *, start_day: date | None = None
) -> Law48Analysis | None:
    """First complete analysis without a confirmed topic delivery."""
    day = start_day or PROGRAM_START
    for number in range(1, TARGET_COUNT + 1):
        try:
            analysis = get_analysis(number)
        except ValueError:
            continue
        if not analysis.content_complete:
            continue
        if not await is_issue_published(session, number, start_day=day):
            return analysis
    return None


async def admin_preview_payload(
    session: AsyncSession,
    settings: Settings,
    *,
    on_date: date | None = None,
) -> dict:
    """Admin-only read model: next unpublished item + gate status. No send."""
    day = on_date or yerevan_today()
    progress = content_progress()
    next_item = await next_unpublished_analysis(session)
    calendar_number = publication_number(day)
    approved = False
    if calendar_number and settings.general_chat_id:
        approved = await series_issue_is_approved(
            session, day, settings.general_chat_id, calendar_number
        )
    preview_number = next_item.law_number if next_item else calendar_number
    preview_html = render_analysis(preview_number) if preview_number else ""
    return {
        "date": day.isoformat(),
        "publish_flag_enabled": publish_enabled(settings),
        "approval_required": True,
        "calendar_number": calendar_number,
        "calendar_approved": approved,
        "would_public_send": bool(
            publish_enabled(settings)
            and approved
            and calendar_number
            and settings.general_chat_id
        ),
        "content_progress": progress,
        "next_unpublished": (
            {
                "law_number": next_item.law_number,
                "title": next_item.title,
                "audio_url": next_item.audio_url,
                "case_study": next_item.case_study,
                "critical_view": next_item.critical_view,
                "discussion_question": next_item.discussion_question,
            }
            if next_item
            else None
        ),
        "preview_html": preview_html,
        "idempotency_keys_example": {
            "topic": topic_delivery_key(PROGRAM_START, preview_number or 1),
            "subscriber": subscriber_delivery_key(PROGRAM_START, preview_number or 1, 0),
            "task_points": task_points_idempotency_key(0, preview_number or 1),
        },
        "note": (
            "Preview only — no channel/chat message is sent by this endpoint. "
            "Public send requires literature_48_laws_publish_enabled=true AND "
            "exact-day series approval."
        ),
    }


# Validate asset at import so broken content fails CI early.
validate_store()
