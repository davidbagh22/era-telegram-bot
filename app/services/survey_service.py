from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.management_models import AdminSurvey, AdminSurveyResponse
from app.database.models import User

# Statuses a participant can still answer under — mirrors
# app/handlers/participant/surveys.py::SURVEY_PARTICIPANT_STATUSES exactly.
PARTICIPANT_VISIBLE_STATUSES = {"active", "sent"}

MONTHLY_SURVEY_TITLE = "Ежемесячный пульс ЭРА"
MONTHLY_SURVEY_DESCRIPTION = (
    "Короткий управленческий опрос для совета и команды. Он помогает понять, "
    "что работает, где участникам нужна поддержка и какие решения важны в следующем месяце."
)
MONTHLY_SURVEY_QUESTIONS = [
    "Что в ЭРА за этот месяц было для Вас самым полезным?",
    "Где было сложно, непонятно или не хватило поддержки?",
    "Какой формат мероприятия или активности Вы хотите видеть в следующем месяце?",
    "Насколько Вам комфортно в коммуникации с командой от 1 до 10? Почему именно так?",
    "В каком направлении Вы хотите быть активнее в следующем месяце?",
    "Что мешает Вам участвовать чаще или брать больше ответственности?",
    "Кого из команды Вы хотите отметить за вклад в этом месяце и почему?",
    "Какую одну вещь совету ЭРА стоит улучшить в следующем месяце?",
]

CONFERENCE_SURVEY_MARKER = "__ERA_CONFERENCE_SPEAKERS__"
CONFERENCE_SURVEY_TITLE = "Кого ты хочешь услышать на молодёжной конференции ЭРА?"
CONFERENCE_SURVEY_DESCRIPTION = (
    "Выбери до 7 спикеров, ради встречи с которыми ты действительно пришёл бы. "
    "Результаты голосования будут учитываться при формировании программы."
)
CONFERENCE_SPEAKER_OPTIONS = [
    {"value": "Юлия Барановская", "label": "Юлия Барановская", "description": "Медиа, публичность, личный бренд и работа с большой аудиторией."},
    {"value": "Егор Бероев", "label": "Егор Бероев", "description": "Творческий путь, профессия и работа над собой."},
    {"value": "Екатерина Климова", "label": "Екатерина Климова", "description": "Карьера, сцена, кино и многолетняя работа в профессии."},
    {"value": "Мария Кожевникова", "label": "Мария Кожевникова", "description": "Публичная карьера, проекты и личный путь."},
    {"value": "Оскар Кучера", "label": "Оскар Кучера", "description": "Телевидение, коммуникации и работа перед камерой."},
    {"value": "Андрей Мерзликин", "label": "Андрей Мерзликин", "description": "Путь в профессии и внутренняя кухня большого кино."},
    {"value": "Дмитрий Харатьян", "label": "Дмитрий Харатьян", "description": "Большая карьера, опыт и работа с разными поколениями зрителей."},
    {"value": "Алексей Чадов", "label": "Алексей Чадов", "description": "Кино от актёрской работы до создания собственного проекта."},
    {"value": "Елизавета Арзамасова", "label": "Елизавета Арзамасова", "description": "Карьера с детства, творчество и социальные проекты."},
    {"value": "Ольга Кузьмина", "label": "Ольга Кузьмина", "description": "Как строится актёрская карьера и жизнь внутри индустрии."},
    {"value": "Вячеслав Манучаров", "label": "Вячеслав Манучаров", "description": "Интервью, медиа и умение раскрывать человека в разговоре."},
    {"value": "Артём Ткаченко", "label": "Артём Ткаченко", "description": "Профессия, роли и творческий поиск."},
    {"value": "Вячеслав Чепурченко", "label": "Вячеслав Чепурченко", "description": "Современное кино и путь молодого артиста."},
    {"value": "Ирина Безрукова", "label": "Ирина Безрукова", "description": "Творчество, коммуникация и личный профессиональный путь."},
    {"value": "Максим Белбородов", "label": "Максим Белбородов", "description": "Современное кино и сериалы, включая «Постучись в мою дверь в Москве»."},
    {"value": "Иван Жвакин", "label": "Иван Жвакин", "description": "Молодёжные проекты, узнаваемость и путь в профессии."},
    {"value": "Валерия Ланская", "label": "Валерия Ланская", "description": "Театр, кино, музыка и работа сразу в нескольких творческих направлениях."},
    {"value": "Никита Павленко", "label": "Никита Павленко", "description": "Кино, сериалы и путь нового поколения российских артистов."},
    {"value": "Владислав Прохоров", "label": "Владислав Прохоров", "description": "Актёр и музыкант, сыграл Сергея Жукова в фильме «Руки вверх!»."},
    {"value": "Александр Сетейкин", "label": "Александр Сетейкин", "description": "Роль Димы Дубина во вселенной «Майора Грома»."},
    {"value": "Анна Савранская", "label": "Анна Савранская", "description": "Молодая карьера и большое кино, одна из главных ролей в «Лёд 3»."},
    {"value": "Владислав Канопка", "label": "Владислав Канопка", "description": "Кино, узнаваемость и работа с молодёжной аудиторией."},
    {"value": "Михаил Башкатов", "label": "Михаил Башкатов", "description": "Юмор, телевидение и умение держать аудиторию."},
    {"value": "Владислав Ценёв", "label": "Владислав Ценёв", "description": "Современное кино, публичность и работа с образом."},
    {"value": "Берта Пяттоева", "label": "Берта Пяттоева", "description": "Чревовещание, авторские куклы и необычный формат."},
    {"value": "Татьяна Шитова", "label": "Татьяна Шитова", "description": "Голос «Алисы» от Яндекса, речь и профессия за кадром."},
    {"value": "Дарья Калмыкова", "label": "Дарья Калмыкова", "description": "Театр, съёмочная площадка и профессиональное развитие."},
    {"value": "Анастасия Попова", "label": "Анастасия Попова", "description": "Современные сериалы, кастинги и работа внутри индустрии."},
    {"value": "Рустам Багизов", "label": "Рустам Багизов", "description": "Публичные выступления, коммуникации и умение продавать свои идеи."},
    {"value": "Сергей Тугушев", "label": "Сергей Тугушев", "description": "Камера, публичность, психология общения и выступлений."},
    {"value": "Светлана Иконникова", "label": "Светлана Иконникова", "description": "Публичные коммуникации, тексты и риторика."},
    {"value": "Тамара Карташева", "label": "Тамара Карташева", "description": "Публичные выступления, риторика, влияние и харизма."},
    {"value": "Алексей Марков", "label": "Алексей Марков", "description": "Актёрское мастерство, уверенность и самопрезентация."},
    {"value": "Владислав Маленко", "label": "Владислав Маленко", "description": "Слово, культура и современная поэзия."},
    {"value": "Олег Рой", "label": "Олег Рой", "description": "Истории, творчество и создание собственного продукта."},
    {"value": "Клим Шипенко", "label": "Клим Шипенко", "description": "Большое кино, масштабные проекты и фильмы нового формата."},
    {"value": "Илья Учитель", "label": "Илья Учитель", "description": "Молодой взгляд на кино и путь от идеи до готового фильма."},
    {"value": "Александр Олешко", "label": "Александр Олешко", "description": "Сцена, телевидение, импровизация и контакт с аудиторией."},
    {"value": "Михаил Мамаев", "label": "Михаил Мамаев", "description": "Творческая карьера, журналистика и большой профессиональный опыт."},
    {"value": "Александр Самойленко", "label": "Александр Самойленко", "description": "Киноиндустрия с точки зрения актёра, режиссёра и продюсера."},
]


def questions_payload(questions: list[str]) -> list[dict[str, Any]]:
    return [{"text": question.strip()} for question in questions if question.strip()]


def conference_questions_payload() -> list[dict[str, Any]]:
    return [
        {
            "text": "Кого ты бы реально пришёл послушать вживую?",
            "type": "multiple_choice",
            "options": CONFERENCE_SPEAKER_OPTIONS,
            "required": True,
            "max_selections": 7,
            "searchable": True,
        },
        {
            "text": "Кого нет в списке, но ради встречи с кем ты бы точно пришёл?",
            "type": "text",
            "required": False,
        },
    ]


def survey_question_specs(survey: AdminSurvey) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in survey.questions_json or []:
        if isinstance(item, str):
            text = item.strip()
            raw: dict[str, Any] = {"text": text}
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("question") or "").strip()
            raw = item
        else:
            continue
        if not text:
            continue
        question_type = str(raw.get("type") or "text").strip()
        if question_type not in {"text", "multiple_choice"}:
            question_type = "text"
        spec: dict[str, Any] = {
            "text": text,
            "type": question_type,
            "required": bool(raw.get("required", True)),
            "options": [],
            "max_selections": None,
            "searchable": False,
        }
        if question_type == "multiple_choice":
            options: list[dict[str, str]] = []
            for option in raw.get("options") or []:
                if isinstance(option, str):
                    value = option.strip()
                    label = value
                    description = ""
                elif isinstance(option, dict):
                    value = str(option.get("value") or option.get("label") or "").strip()
                    label = str(option.get("label") or value).strip()
                    description = str(option.get("description") or "").strip()
                else:
                    continue
                if value and label:
                    options.append({"value": value, "label": label, "description": description})
            spec["options"] = options
            max_selections = raw.get("max_selections")
            spec["max_selections"] = max_selections if isinstance(max_selections, int) and max_selections > 0 else None
            spec["searchable"] = bool(raw.get("searchable", False))
        result.append(spec)
    return result


def survey_questions(survey: AdminSurvey) -> list[str]:
    return [spec["text"] for spec in survey_question_specs(survey)]


def parse_survey_text(raw: str) -> tuple[str, str | None, list[dict[str, Any]]]:
    """Parse admin-friendly survey text.

    Format:
    Title
    Optional description
    ---
    Question 1
    Question 2
    """
    value = (raw or "").strip()
    before, _, after = value.partition("---")
    header_lines = [line.strip() for line in before.splitlines() if line.strip()]
    question_lines = [line.strip() for line in after.splitlines() if line.strip()]
    if not header_lines:
        raise ValueError("title_required")
    title = header_lines[0][:255]
    description = "\n".join(header_lines[1:]).strip() or None
    if not question_lines:
        question_lines = header_lines[1:]
        description = None
    questions = questions_payload(question_lines)
    if not questions:
        raise ValueError("questions_required")
    return title, description, questions


def answer_items(response: Any) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in getattr(response, "answers_json", None) or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if question or answer:
            result.append({"question": question, "answer": answer})
    return result


def validate_answers(survey: AdminSurvey, answers: list[str]) -> list[str]:
    specs = survey_question_specs(survey)
    if len(answers) != len(specs):
        raise ValueError("all_answers_required")
    normalized: list[str] = []
    for spec, raw_answer in zip(specs, answers, strict=True):
        value = (raw_answer or "").strip()
        if spec["type"] == "text":
            if spec["required"] and not value:
                raise ValueError("all_answers_required")
            normalized.append(value)
            continue
        try:
            selected_raw = json.loads(value) if value else []
        except json.JSONDecodeError as exc:
            raise ValueError("invalid_multiple_choice_answer") from exc
        if not isinstance(selected_raw, list) or any(not isinstance(item, str) for item in selected_raw):
            raise ValueError("invalid_multiple_choice_answer")
        selected: list[str] = []
        for item in selected_raw:
            choice = item.strip()
            if choice and choice not in selected:
                selected.append(choice)
        allowed = {option["value"] for option in spec["options"]}
        if any(choice not in allowed for choice in selected):
            raise ValueError("invalid_multiple_choice_answer")
        if spec["required"] and not selected:
            raise ValueError("all_answers_required")
        max_selections = spec["max_selections"]
        if max_selections is not None and len(selected) > max_selections:
            raise ValueError("too_many_selections")
        normalized.append(json.dumps(selected, ensure_ascii=False))
    return normalized


# -- Participant-facing (Mini App equivalent of app/handlers/participant/surveys.py) --


async def list_visible_surveys(session: AsyncSession) -> list[AdminSurvey]:
    return list(
        (
            await session.scalars(
                select(AdminSurvey)
                .where(AdminSurvey.status.in_(PARTICIPANT_VISIBLE_STATUSES))
                .order_by(AdminSurvey.sent_at.desc().nullslast(), AdminSurvey.created_at.desc())
            )
        ).all()
    )


async def get_response(session: AsyncSession, survey_id: int, user_id: int) -> AdminSurveyResponse | None:
    return await session.scalar(
        select(AdminSurveyResponse).where(
            AdminSurveyResponse.survey_id == survey_id, AdminSurveyResponse.user_id == user_id
        )
    )


async def submit_survey(
    session: AsyncSession, survey: AdminSurvey, user: User, answers: list[str]
) -> AdminSurveyResponse:
    """One row per (survey, user); structured choices remain JSON strings for compatibility."""
    payload = [
        {"question": question, "answer": answer}
        for question, answer in zip(survey_questions(survey), answers, strict=True)
    ]
    now = datetime.now().astimezone()
    existing = await get_response(session, survey.id, user.id)
    if existing:
        existing.answers_json = payload
        existing.status = "completed"
        existing.submitted_at = now
        return existing
    response = AdminSurveyResponse(
        survey_id=survey.id, user_id=user.id, answers_json=payload, status="completed", submitted_at=now
    )
    session.add(response)
    await session.flush()
    return response