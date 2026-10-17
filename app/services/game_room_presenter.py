"""Public game cards use Telegram identities, never registration questionnaire data."""
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo


MODE_LABELS = {
    "solo": "⚡ Быстрый квиз", "team": "🤝 Командный квиз", "duel": "🏆 Командная дуэль",
    "true_or_myth": "✅ Правда или миф", "guess_country": "🌍 Угадай страну",
    "chronology": "🕰 Хронология", "word_chain": "🔤 Словесная цепочка",
    "associations": "💭 Ассоциации", "logic": "🧠 Логика",
    "culture": "🎭 Культурный блиц", "memory": "🧩 Память",
}


def remember_player(room: dict, telegram_user) -> None:
    # The name is already public in Telegram. Do not expose private profile fields.
    name = " ".join(filter(None, (telegram_user.first_name, telegram_user.last_name)))
    name = " ".join(name.split())[:60] or "Участник"
    room.setdefault("players", {})[str(telegram_user.id)] = name


def player_label(room: dict, uid: int) -> str:
    raw = room.get("players", {}).get(str(uid)) or "Профиль Telegram"
    name = escape(raw[:30] + ("…" if len(raw) > 30 else ""))
    return f'<a href="tg://user?id={int(uid)}">{name}</a> · <code>{int(uid)}</code>'


def room_heading(room: dict) -> str:
    label = MODE_LABELS.get(room.get("mode") or room.get("kind"), "🎮 Игра ЭРА")
    return f"<b>{label}</b>"


def roster(room: dict, *, result: bool = False) -> str:
    participants = room.get("participants", [])
    ready = room.get("ready", [])
    answers = room.get("answers", {})
    scores = room.get("scores", {})

    def member(uid):
        if result:
            suffix = f" — {scores.get(str(uid), 0)} очк."
            if str(uid) in (room.get("rewards") or {}):
                suffix += f" · ЭРА +{room['rewards'].get(str(uid), 0)}"
        elif room.get("status") == "playing":
            suffix = " · ✅ ответ принят" if str(uid) in answers else " · ⏳ отвечает"
        else:
            suffix = " · ✅ готов" if uid in ready else " · ⏳ не готов"
        leader = result and len(participants) > 1 and room.get("kind") != "duel" and scores.get(str(uid), 0) == max(scores.values(), default=0)
        return ("🏅 " if leader else "") + player_label(room, uid) + suffix

    if room.get("kind") == "duel":
        sections = []
        for team, title in (("A", "🔴 Команда А"), ("B", "🔵 Команда Б")):
            members = [uid for uid in participants if room.get("teams", {}).get(str(uid)) == team]
            score = room.get("team_scores", {}).get(team, 0)
            sections.append(f"<b>{title} · {score} очк.</b>\n" + (
                "\n".join(member(uid) for uid in members) if members else "Пока нет игроков"
            ))
        return "\n\n".join(sections)
    title = "Игрок" if len(participants) == 1 else "Состав команды"
    return f"<b>{title}</b>\n" + "\n".join(member(uid) for uid in participants)


def deadline(room: dict) -> str:
    # Explicit duration avoids confusing a participant's device timezone with the server's.
    value = datetime.fromisoformat(room["expires_at"]).astimezone(ZoneInfo("Europe/Moscow")).strftime("%H:%M:%S")
    return f"⏱ До {value} МСК. Ответы — кнопками под карточкой."


def result_summary(room: dict) -> str:
    scores = room.get("scores", {})
    players = room.get("participants", [])
    if room.get("kind") == "duel":
        totals = room.get("team_scores", {"A": 0, "B": 0})
        if totals.get("A", 0) == totals.get("B", 0):
            return "🤝 Ничья!"
        team = "A" if totals.get("A", 0) > totals.get("B", 0) else "B"
        title = "🔴 Команда А" if team == "A" else "🔵 Команда Б"
        winners = [player_label(room, uid) for uid in players if room.get("teams", {}).get(str(uid)) == team]
        return f"🏆 <b>Победила {title}!</b>\n" + "\n".join(winners)
    if len(players) == 1:
        return f"Результат: {scores.get(str(players[0]), 0)} из {len(room.get('questions', []))}."
    best = max(scores.values(), default=0)
    winners = [player_label(room, uid) for uid in players if scores.get(str(uid), 0) == best]
    title = "🏆 Лучший результат" if len(winners) == 1 else "🤝 Лучший результат разделили"
    return f"{title}: {best} очк.\nУчастники отмечены 🏅 в составе команды."
