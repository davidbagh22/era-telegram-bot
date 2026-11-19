"""Telegram HTML presentation for event topics and the November digest.

Keep URL strings behind labels; retain plain data in event records and never
store Telegram formatting in participant-entered descriptions.
"""
from __future__ import annotations

import re
from html import escape

NOVEMBER_KIND = {
    23: ("📜", "Семинар и разговор о литературе памяти"),
    24: ("🎭", "Поэзия, живопись и театр Серебряного века"),
    25: ("📖", "Круглый стол о литературе и философии"),
    28: ("🚀", "Практические мастер-классы для молодёжи"),
}


def _link(label: str, url: str | None) -> str:
    href = str(url or "").strip()
    if not href.startswith("https://t.me/"):
        return ""
    return f'<a href="{escape(href, quote=True)}">{escape(label)}</a>'


def _body(text: str) -> str:
    paragraphs = []
    for line in str(text or "").strip().splitlines():
        value = line.strip()
        if not value:
            paragraphs.append("")
            continue
        match = re.match(r"^(\\d{1,2}:\\d{2})\\s*[—–-]\\s*(.+)$", value)
        if match:
            paragraphs.append(f"• <b>{escape(match.group(1))}</b> — {escape(match.group(2))}")
        else:
            paragraphs.append(escape(value))
    return "\n".join(paragraphs).strip()


def _kind(event):
    marker = str(getattr(event, "additional_info", "") or "")
    if marker.startswith("november-2026-moscow-house:"):
        try:
            return NOVEMBER_KIND.get(int(marker.rsplit(":", 1)[-1]))
        except ValueError:
            pass
    return None


def event_topic_html(event, experience, *, registration: str, chat: str | None, topic: str | None) -> str:
    kind = _kind(event)
    emoji, subtitle = kind if kind is not None else ("✨", "Присоединяйтесь к встрече ЭРА")
    title = str(event.title).strip()
    description = str(getattr(experience, "full_description", "") or event.description or "").strip()
    if description.split("\n", 1)[0].strip() == title:
        description = description.split("\n", 1)[-1].strip()
    ends = getattr(experience, "end_time", None)
    clock = f"{event.event_time:%H:%M}" + (f"–{ends:%H:%M}" if ends else "")
    if _kind(event):
        date_label = f"{event.event_date.day} ноября · {clock}"
    else:
        date_label = f"{event.event_date:%d.%m.%Y} · {clock}"

    lines = [
        f"{emoji} <b>{escape(title)}</b>",
        f"<i>{escape(subtitle)}</i>",
        "",
        _body(description),
        "",
        f"🗓 <b>{escape(date_label)}</b>",
        f"📍 {escape(str(event.location))}",
        "",
        "<i>Для участия необходима регистрация.</i>",
    ]
    actions = [_link("Зарегистрироваться", registration), _link("Обсуждение проекта", topic),
               _link("Общий чат ЭРА", chat)]
    actions = [link for link in actions if link]
    if actions:
        lines.append("🔗 " + " · ".join(actions))
    return "\n".join(lines)


def november_digest_html(items: list[tuple], *, chat: str | None) -> str:
    """One compact digest: event/date and two named links per programme item."""
    lines = [
        "✨ <b>ЧЕТЫРЕ СОБЫТИЯ — ЧЕТЫРЕ ПОВОДА ВСТРЕТИТЬСЯ</b>",
        "<i>23–28 ноября · Дом Москвы в Ереване</i>",
        "",
        "Четыре формата, новые знания и люди, с которыми хочется создавать проекты.",
    ]
    for event, exp, registration in items:
        kind = _kind(event)
        emoji = kind[0] if kind else "✨"
        clock = f"{event.event_time:%H:%M}"
        end_time = getattr(exp, "end_time", None)
        if end_time:
            clock += f"–{end_time:%H:%M}"
        lines.extend([
            "",
            f"{emoji} <b>{event.event_date.day} НОЯБРЯ · {clock}</b>",
            f"<b>{escape(str(event.title))}</b>",
        ])
        links = [_link("Регистрация", registration),
                 _link("Обсуждение", getattr(exp, "chat_url", None))]
        lines.append(" · ".join(item for item in links if item))
    lines.extend([
        "",
        "🏅 <i>Участникам мастер-классов 28 ноября предусмотрены сертификаты.</i>",
        "📍 <b>Дом Москвы</b> · Ереван, ул. Аргишти, 7",
        "",
        "<i>Выбирайте одну встречу или сразу несколько. Регистрация обязательна.</i>",
    ])
    chat_link = _link("Общий чат ЭРА", chat)
    if chat_link:
        lines.append(f"💬 {chat_link}")
    return "\n".join(lines)
