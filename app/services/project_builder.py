from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProjectQuestion:
    key: str
    block: str
    title: str
    prompt: str
    input_type: str = "text"
    # Kept only for API/test compatibility. The product no longer provides
    # AI-authored answers in the project constructor, so every question uses None.
    ai_hint: str | None = None


# The constructor teaches project logic instead of writing a project for the
# participant. Existing answers live in JSON, so new steps do not require a DB
# migration. Removed/renamed historical keys are preserved below as legacy data.
PROJECT_QUESTIONS = (
    ProjectQuestion(
        "idea",
        "1 · Идея",
        "В чём идея?",
        "Что вы создаёте, для кого и зачем? Опишите суть одним-двумя предложениями своими словами.",
    ),
    ProjectQuestion(
        "title",
        "2 · Название",
        "Как будет называться проект?",
        "Дайте короткое рабочее название, которое легко произнести и запомнить. Его можно изменить позже.",
    ),
    ProjectQuestion(
        "problem",
        "3 · Проблема",
        "Какую ситуацию нужно изменить?",
        "Опишите наблюдаемую ситуацию: кого она касается, с чем эти люди сталкиваются и к чему это приводит.",
    ),
    ProjectQuestion(
        "target_audience",
        "4 · Аудитория",
        "Для кого этот проект?",
        "Опишите конкретную группу: возраст или положение, интересы, потребность и почему проект нужен именно этим людям.",
    ),
    ProjectQuestion(
        "goal",
        "5 · Цель",
        "Что должно измениться благодаря проекту?",
        "Сформулируйте одно главное изменение. «Провести мероприятие» — действие, а не цель.",
    ),
    ProjectQuestion(
        "project_tasks",
        "6 · Задачи",
        "Что нужно сделать, чтобы прийти к цели?",
        "Сформулируйте 3–7 основных задач проекта. Это направления работы, а не мелкий чек-лист команды.",
    ),
    ProjectQuestion(
        "format",
        "7 · Формат",
        "Что непосредственно будет происходить с участником?",
        "Опишите формат: мастер-класс, игра, квест, конкурс, форум, акселератор, медиапроект, выставка, программа, серия встреч или другой реальный вариант.",
    ),
    ProjectQuestion(
        "uniqueness",
        "8 · Уникальность",
        "Почему человек выберет именно этот проект?",
        "Опишите конкретное отличие или механику. Не ограничивайтесь словами «уникальный», «современный» или «интересный».",
    ),
    ProjectQuestion(
        "scenario",
        "9 · Механика",
        "Как пройдёт путь участника?",
        "Опишите ключевые действия человека от входа в проект до финала: что он делает, где включается и с чем уходит.",
    ),
    ProjectQuestion(
        "team",
        "10 · Команда",
        "Какие функции нужны в команде?",
        "Сначала определите функции: руководитель, координатор, партнёрства, медиа, техническая часть, волонтёры и другие нужные роли. Затем укажите только реальных людей.",
    ),
    ProjectQuestion(
        "partners",
        "11 · Партнёры",
        "Какие партнёры и ресурсы нужны?",
        "Партнёр нужен не ради логотипа. Укажите подтверждённых партнёров и конкретный ресурс каждого. Если их пока нет — напишите «Партнёры пока не определены».",
    ),
    ProjectQuestion(
        "resources",
        "12 · Ресурсы",
        "Что понадобится для реализации?",
        "Перечислите реальные ресурсы: площадка, оборудование, материалы, люди, информационная поддержка и другое. Неизвестное можно честно отметить как неопределённое.",
    ),
    ProjectQuestion(
        "budget",
        "13 · Бюджет",
        "Из каких расходов складывается проект?",
        "Сначала перечислите категории расходов: площадка, оборудование, материалы, печать, питание, логистика, специалисты, продвижение, техническая часть, резерв. Стоимость указывайте только если она уже известна.",
    ),
    ProjectQuestion(
        "implementation_plan",
        "14 · План реализации",
        "Какая последовательность приведёт к запуску?",
        "Опишите основные этапы от текущей точки до завершения проекта. Не придумывайте сроки и ответственных, если они ещё не определены.",
    ),
    ProjectQuestion(
        "promotion",
        "15 · Продвижение",
        "Как нужные люди узнают о проекте?",
        "Определите, кого привлекаете, где эта аудитория находится, каким сообщением, кто отвечает и когда должно начаться продвижение.",
    ),
    ProjectQuestion(
        "expected_result",
        "16 · Результаты",
        "Что должно получиться после проекта?",
        "Разделите результат на количественный — то, что можно посчитать, и качественный — то, что должно измениться. Не придумывайте цифры.",
    ),
    ProjectQuestion(
        "success_metrics",
        "17 · Показатели",
        "Как вы поймёте, что результат получен?",
        "Для каждого важного результата укажите реальный способ проверки: регистрация, посещение, выполненные действия, обратная связь, повторное участие или другой доступный источник.",
    ),
    ProjectQuestion(
        "risks",
        "18 · Риски",
        "Что может помешать и что вы будете делать?",
        "Опишите несколько реальных рисков по схеме: риск → вероятность → последствия → решение.",
    ),
)


LEGACY_FIELD_LABELS = {
    "department_direction": "Отдел и направление",
    "audience_need": "Потребность аудитории",
    "differentiator": "Фишка проекта",
    "venue_request": "Площадка",
    "proposed_date": "Предложенная дата",
    "proposed_time": "Предложенное время",
    "marketing_plan": "Старый план продвижения",
    "announcement": "Анонс",
    "participant_reminder": "Сообщение участникам",
    "follow_up_plan": "План после проекта",
    "activities": "Активности старой версии конструктора",
    "tasks": "Задания старой версии конструктора",
    "points": "Баллы старой версии конструктора",
}


def question_text(index: int) -> str:
    question = PROJECT_QUESTIONS[index]
    return (
        f"{question.block}\n"
        f"Шаг {index + 1} из {len(PROJECT_QUESTIONS)}\n\n"
        f"{question.title}\n\n{question.prompt}"
    )


def render_project_document(
    data: dict[str, Any], author_name: str, telegram: str
) -> str:
    def value(key: str) -> Any:
        return data.get(key) or "Не указано"

    legacy_lines = []
    current_keys = {question.key for question in PROJECT_QUESTIONS}
    for key, label in LEGACY_FIELD_LABELS.items():
        if key not in current_keys and data.get(key):
            legacy_lines.append(f"{label}\n{data[key]}")
    legacy = "\n\n".join(legacy_lines)
    if legacy:
        legacy = f"\n\nРАНЕЕ ЗАПОЛНЕННЫЕ ДАННЫЕ\n\n{legacy}"

    return f"""ПРОЕКТ ЭРА

Автор: {author_name}
Telegram: {telegram}

1. ИДЕЯ
{value("idea")}

2. НАЗВАНИЕ
{value("title")}

3. ПРОБЛЕМА
{value("problem")}

4. ЦЕЛЕВАЯ АУДИТОРИЯ
{value("target_audience")}

5. ЦЕЛЬ
{value("goal")}

6. ЗАДАЧИ
{value("project_tasks")}

7. ФОРМАТ
{value("format")}

8. УНИКАЛЬНОСТЬ
{value("uniqueness")}

9. МЕХАНИКА / ПУТЬ УЧАСТНИКА
{value("scenario")}

10. КОМАНДА
{value("team")}

11. ПАРТНЁРЫ
{value("partners")}

12. РЕСУРСЫ
{value("resources")}

13. БЮДЖЕТ
{value("budget")}

14. ПЛАН РЕАЛИЗАЦИИ
{value("implementation_plan")}

15. ПРОДВИЖЕНИЕ
{value("promotion")}

16. РЕЗУЛЬТАТЫ
{value("expected_result")}

17. ПОКАЗАТЕЛИ
{value("success_metrics")}

18. РИСКИ
{value("risks")}

19. ФИНАЛЬНЫЙ PREVIEW
Проект собран из подтверждённых ответов автора.{legacy}
"""
