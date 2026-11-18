"""Public game cards use Telegram identities, never registration questionnaire data."""
from html import escape
from typing import TypedDict


MODE_LABELS = {
    "solo": "⚡ Быстрый квиз", "team": "🤝 Командный квиз", "duel": "🏆 Командная дуэль",
    "true_or_myth": "✅ Правда или миф", "guess_country": "🌍 Угадай страну",
    "chronology": "🕰 Хронология", "word_chain": "🔤 Словесная цепочка",
    "associations": "💭 Ассоциации", "logic": "🧠 Логика",
    "culture": "🎭 Культурный блиц", "memory": "🧩 Память",
    "spyfall": "🕵 Шпион",
}


class GameCardMeta(TypedDict):
    players: str
    minutes: str
    rules: str
    group: bool


# Selection-card copy for Досуг → Игры (players · duration · one-line rules).
GAME_CARDS: dict[str, GameCardMeta] = {
    "solo": {"players": "1", "minutes": "3–5", "rules": "5 вопросов, отвечаете кнопками", "group": False},
    "true_or_myth": {"players": "1", "minutes": "1–2", "rules": "Одно утверждение: правда или миф", "group": False},
    "guess_country": {"players": "1", "minutes": "1–3", "rules": "Угадайте страну; можно взять подсказки", "group": False},
    "chronology": {"players": "1", "minutes": "1–2", "rules": "Расставьте события по порядку", "group": False},
    "word_chain": {"players": "1", "minutes": "1–2", "rules": "Продолжите цепочку слов", "group": False},
    "associations": {"players": "1", "minutes": "1–3", "rules": "Найдите общее; подсказки по желанию", "group": False},
    "logic": {"players": "1", "minutes": "1–3", "rules": "Одно логическое задание", "group": False},
    "culture": {"players": "1", "minutes": "1–2", "rules": "Короткий вопрос про культуру", "group": False},
    "memory": {"players": "1", "minutes": "1–2", "rules": "Запомните ряд за 5 секунд", "group": False},
    "team": {"players": "2–8", "minutes": "5–10", "rules": "Общая тема: все отвечают сами", "group": True},
    "duel": {"players": "2–8", "minutes": "5–10", "rules": "Две команды; бот делит состав", "group": True},
    "spyfall": {"players": "3–8", "minutes": "8–15", "rules": "Найдите шпиона в общей теме", "group": True},
}


def game_card_line(mode: str) -> str:
    meta = GAME_CARDS.get(mode)
    label = MODE_LABELS.get(mode, "🎮 Игра ЭРА")
    if not meta:
        return label
    kind = "группа" if meta["group"] else "соло"
    return (
        f"<b>{label}</b>\n"
        f"{meta['players']} игр. · ~{meta['minutes']} мин · {kind}\n"
        f"{meta['rules']}"
    )


def remember_player(room: dict, telegram_user) -> None:
    # The name is already public in Telegram. Do not expose private profile fields.
    name = " ".join(filter(None, (telegram_user.first_name, telegram_user.last_name)))
    name = " ".join(name.split())[:60] or "Участник"
    room.setdefault("players", {})[str(telegram_user.id)] = name


def player_label(room: dict, uid: int) -> str:
    raw = room.get("players", {}).get(str(uid)) or "Профиль Telegram"
    name = escape(raw[:30] + ("…" if len(raw) > 30 else ""))
    return f'<a href="tg://user?id={int(uid)}">{name}</a>'


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
            suffix = " · ответил" if str(uid) in answers else " · думает"
        else:
            suffix = " · готов" if uid in ready else " · ждём"
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
    # Keep the card useful across time zones and avoid stale absolute timestamps.
    return "⏱ Ответь кнопкой ниже"


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
