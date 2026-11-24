"""Four additional community missions — brings the catalog to 30 without
rewriting the compressed 26-item pack. Seeded idempotently by code."""

from __future__ import annotations

EXTRA_COMMUNITY_MISSIONS: list[dict] = [
    {
        "code": "M7.1",
        "month": 7,
        "category": "community",
        "claim_mode": "SOLO_OR_TEAM",
        "min_people": 1,
        "max_people": 3,
        "workspace_chat_key": "general",
        "deadline_days": 10,
        "points": 120,
        "counts_toward": ["community"],
        "title": "Тёплый вход для новичка",
        "description": (
            "Выбери одного нового участника ЭРА и проведи его через первый "
            "понятный шаг: объяснить, куда писать, какое ближайшее событие "
            "подойдёт, и помочь записаться.\n\n"
            "Результат: короткий отчёт — кто, какой шаг сделан, что сработало."
        ),
        "deliverable": "Отчёт о первом шаге новичка",
        "repeatable": True,
    },
    {
        "code": "M7.2",
        "month": 7,
        "category": "culture",
        "claim_mode": "TEAM",
        "min_people": 2,
        "max_people": 5,
        "workspace_chat_key": "internal",
        "deadline_days": 14,
        "points": 150,
        "counts_toward": ["culture"],
        "title": "Вечер историй ЭРА",
        "description": (
            "Собери 5 коротких живых историй участников (не лозунги): зачем "
            "пришли, что изменилось, чему научились. Оформи как вечер или "
            "пост-подборку.\n\n"
            "Результат: 5 историй + формат показа."
        ),
        "deliverable": "5 историй и формат показа",
        "repeatable": True,
    },
    {
        "code": "M7.3",
        "month": 7,
        "category": "media",
        "claim_mode": "SOLO",
        "min_people": 1,
        "max_people": 1,
        "workspace_chat_key": "media",
        "deadline_days": 7,
        "points": 100,
        "counts_toward": ["media"],
        "title": "Карта «куда пойти в ЭРА»",
        "description": (
            "Сделай понятную одноэкранную схему для новичка: события, проекты, "
            "задания, вектор, портфолио — куда нажать и зачем.\n\n"
            "Результат: картинка или текст-схема + подпись «с чего начать»."
        ),
        "deliverable": "Одноэкранная схема входа",
        "repeatable": True,
    },
    {
        "code": "M7.4",
        "month": 7,
        "category": "social",
        "claim_mode": "TEAM",
        "min_people": 2,
        "max_people": 4,
        "workspace_chat_key": "external",
        "deadline_days": 12,
        "points": 160,
        "counts_toward": ["social"],
        "title": "Польза за выходные",
        "description": (
            "Организуй маленькое полезное действие вне ЭРА (помощь, сбор, "
            "экскурсия, мастер-класс) с понятным результатом для людей рядом.\n\n"
            "Результат: фото/отчёт + что изменилось для участников."
        ),
        "deliverable": "Отчёт о социальном результате",
        "repeatable": True,
    },
]


def load_extra_community_missions() -> list[dict]:
    return list(EXTRA_COMMUNITY_MISSIONS)
