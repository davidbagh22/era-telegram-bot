from __future__ import annotations

from typing import Any

from app.database.management_models import AdminSurvey

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


def questions_payload(questions: list[str]) -> list[dict[str, str]]:
    return [{"text": question.strip()} for question in questions if question.strip()]


def survey_questions(survey: AdminSurvey) -> list[str]:
    result: list[str] = []
    for item in survey.questions_json or []:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("question") or "").strip()
        else:
            text = ""
        if text:
            result.append(text)
    return result


def parse_survey_text(raw: str) -> tuple[str, str | None, list[dict[str, str]]]:
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
