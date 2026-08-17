from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.development_models import (
    AdminVisibilitySetting,
    AssessmentConsent,
    AssessmentDefinition,
    DevelopmentAuditLog,
    DevelopmentGoal,
    GoalReview,
    MonthlyCheckin,
    MonthlyContext,
    PersonalInsight,
    PersonalNote,
    RecommendationHistory,
    UserVectorProfile,
    WeeklyPulse,
)
from app.database.models import User
from app.services.digital_engagement_service import (
    award_goal_completed,
    award_goal_set,
    award_vector_monthly_checkin,
    award_vector_weekly_pulse,
)
from app.utils.constants import ApplicationStatus

CONSENT_VERSION = "MY_VECTOR_V1"
STATE_METHOD_VERSION = "ERA_STATE_CORE_V2_ADAPTIVE"
STATE_DIMENSIONS = ("energy", "agency", "autonomy", "connection", "direction")

STATE_LABELS = {
    "energy": "Энергия",
    "agency": "Опора",
    "autonomy": "Самостоятельность",
    "connection": "Связь",
    "direction": "Направление",
}

STATE_QUESTIONS = [
    {"code": "energy", "title": "Энергия", "text": "За последние две недели у меня хватало энергии на обычные дела."},
    {"code": "agency", "title": "Опора", "text": "Когда появлялась сложная задача, я чувствовал, что могу найти первый шаг."},
    {"code": "autonomy", "title": "Самостоятельность", "text": "В важных для меня ситуациях я чаще принимал решения, которые действительно считал своими."},
    {"code": "connection", "title": "Связь", "text": "Я чувствовал, что рядом есть люди, с которыми могу быть собой и обратиться за поддержкой."},
    {"code": "direction", "title": "Направление", "text": "Я понимал, на чём хочу сосредоточиться в ближайшее время."},
]

# These questions never enter the five-part state index. They exist only to
# make the monthly return adaptive and to give the deterministic
# interpretation layer more context than a repeated five-score form.
FOLLOWUP_QUESTIONS: dict[str, dict[str, str]] = {
    "agency_start": {"code": "agency_start", "title": "Первый шаг", "text": "Мне было достаточно легко начать важное дело самому, не дожидаясь чужого толчка."},
    "initiative_first": {"code": "initiative_first", "title": "Инициатива", "text": "Когда нужна была инициатива, я хотя бы иногда предлагал первый конкретный шаг сам."},
    "autonomy_others": {"code": "autonomy_others", "title": "Своё решение", "text": "Перед тем как спрашивать мнение других, я обычно успевал сформулировать собственную позицию."},
    "energy_load": {"code": "energy_load", "title": "Нагрузка", "text": "Я мог заметить лишнюю нагрузку и убрать хотя бы часть дел без сильного чувства вины."},
    "rest_guilt": {"code": "rest_guilt", "title": "Восстановление", "text": "Я позволял себе восстанавливаться до того, как усталость становилась совсем сильной."},
    "connection_depth": {"code": "connection_depth", "title": "Контакт", "text": "За последнее время у меня был хотя бы один разговор, после которого я чувствовал настоящую связь с человеком."},
    "ask_help": {"code": "ask_help", "title": "Поддержка", "text": "Когда мне действительно была нужна помощь, я мог попросить о ней прямо и конкретно."},
    "direction_choice": {"code": "direction_choice", "title": "Фокус", "text": "Из нескольких важных дел я мог выбрать одно главное, а не пытаться держать всё одновременно."},
    "finish_visibility": {"code": "finish_visibility", "title": "Доведение", "text": "Я продолжал работу даже тогда, когда результат появлялся не сразу."},
    "newness_uncertainty": {"code": "newness_uncertainty", "title": "Новое", "text": "Мне было нормально пробовать небольшое новое действие, даже если результат заранее неясен."},
}

THEME_QUESTIONS = [
    {"code": "theme_baseline", "theme": "Карта старта", "title": "Наблюдение", "text": "В этом месяце я чаще замечал, какие условия помогают мне включаться и чувствовать себя собой."},
    {"code": "theme_energy", "theme": "Энергия", "title": "Ресурс", "text": "Я замечал, какие дела в этом месяце давали мне энергию, а какие заметно её забирали."},
    {"code": "theme_action", "theme": "Действие", "title": "Движение", "text": "Мне удавалось превращать намерение хотя бы в один маленький видимый результат."},
    {"code": "theme_people", "theme": "Люди", "title": "Люди", "text": "В общении я мог оставаться в контакте с людьми и одновременно не терять собственную позицию."},
    {"code": "theme_interest", "theme": "Интерес", "title": "Любопытство", "text": "Я замечал, к каким занятиям возвращаюсь из настоящего интереса, а не только потому, что «надо»."},
    {"code": "theme_halfyear", "theme": "Полугодие", "title": "Изменение", "text": "По сравнению с началом моего пути я уже могу назвать хотя бы одно изменение, которое действительно замечаю в себе."},
    {"code": "theme_newness", "theme": "Новое", "title": "Эксперимент", "text": "В этом месяце я позволял себе хотя бы один безопасный эксперимент без гарантированного результата."},
    {"code": "theme_autonomy", "theme": "Самостоятельность", "title": "Выбор", "text": "Хотя бы одно важное решение в этом месяце я принял потому, что сам считал его правильным для себя."},
    {"code": "theme_persistence", "theme": "Устойчивость действия", "title": "Длинный шаг", "text": "Я мог возвращаться к важному делу после паузы или препятствия, а не считать его автоматически проваленным."},
    {"code": "theme_environment", "theme": "Среда", "title": "Условия", "text": "Я лучше понимал, в каких условиях проявляюсь сильнее: один, с людьми, при свободе или при понятной структуре."},
    {"code": "theme_values", "theme": "Что стало важнее", "title": "Важное", "text": "Я мог яснее отличить то, что действительно важно мне сейчас, от вещей, которые просто требуют внимания."},
    {"code": "theme_year", "theme": "Мой год", "title": "Год", "text": "Оглядываясь назад, я могу назвать то, что теперь понимаю о себе точнее, чем в начале года."},
]

QUESTION_BY_CODE = {
    item["code"]: item
    for item in [*STATE_QUESTIONS, *FOLLOWUP_QUESTIONS.values(), *THEME_QUESTIONS]
}

ANSWER_OPTIONS = [
    {"value": 0, "label": "Совсем не похоже"},
    {"value": 1, "label": "Скорее нет"},
    {"value": 2, "label": "По-разному"},
    {"value": 3, "label": "Скорее да"},
    {"value": 4, "label": "Очень похоже"},
]

CONTEXT_OPTIONS = [
    "учёба", "работа", "семья", "отношения", "друзья", "здоровье", "деньги",
    "неопределённость", "новая возможность", "важное достижение", "конфликт",
    "смена среды", "отдых", "другое", "не хочу отвечать",
]

DEVELOPMENT_WANTS = [
    "уверенность", "выступления", "общение", "новый навык", "дисциплина",
    "лидерство", "собственные проекты", "карьера", "творчество",
    "новые знакомства", "умение отдыхать", "самостоятельность", "другое",
]

# Legacy metadata registry retained for internal documentation compatibility.
# The actual production assessment definitions are seeded by assessment_service
# from assessment_catalog.py and still pass the explicit license gate there.
ASSESSMENT_CATALOG = [
    {"code":"WHO5_RU","title":"Как мне сейчас?","description":"Субъективное благополучие за последние две недели.","source":"World Health Organization","methodology":"WHO-5 Well-Being Index","license":"CC BY-NC-SA 3.0; Russian wording requires approved source","license_status":"methodology_review","estimated_minutes":2,"min_age":None,"retake":14,"construct":"state"},
    {"code":"GSE_RU","title":"Насколько я верю, что справлюсь?","description":"Общая воспринимаемая самоэффективность.","source":"Schwarzer & Jerusalem","methodology":"General Self-Efficacy Scale","license":"Use only an approved Russian adaptation and documented terms","license_status":"methodology_review","estimated_minutes":4,"min_age":12,"retake":60,"construct":"state"},
    {"code":"IPIP_BIG5_RU","title":"Как я устроен?","description":"Пять широких особенностей личности без «хороших» и «плохих» типов.","source":"International Personality Item Pool","methodology":"IPIP Big Five representation — exact scale must be fixed before release","license":"IPIP items are public domain","license_status":"methodology_review","estimated_minutes":8,"min_age":None,"retake":180,"construct":"trait"},
    {"code":"ONET_RIASEC_RU","title":"Что мне действительно интересно?","description":"Шесть направлений интересов RIASEC.","source":"O*NET Resource Center","methodology":"O*NET Interest Profiler / RIASEC","license":"O*NET Career Exploration Tools license; modification rules apply","license_status":"methodology_review","estimated_minutes":7,"min_age":None,"retake":120,"construct":"interest"},
    {"code":"BPNSS_RU","title":"Чего мне сейчас не хватает?","description":"Самостоятельность, ощущение компетентности и связь с людьми.","source":"Self-Determination Theory","methodology":"Basic Psychological Need Satisfaction Scale","license":"Exact Russian adaptation and terms must be approved","license_status":"methodology_review","estimated_minutes":6,"min_age":None,"retake":45,"construct":"state"},
    {"code":"IPIP_FOLLOW_THROUGH_RU","title":"Как я начинаю и довожу","description":"Стиль действия: порядок, настойчивость, стремление к результату.","source":"International Personality Item Pool","methodology":"Selected IPIP facets — exact version pending methodology review","license":"IPIP items are public domain","license_status":"methodology_review","estimated_minutes":6,"min_age":None,"retake":120,"construct":"trait"},
    {"code":"IPIP_SOCIAL_RU","title":"Как я проявляюсь среди людей","description":"Отделяет любовь к общению от готовности проявляться первым.","source":"International Personality Item Pool","methodology":"Selected IPIP social facets — exact version pending methodology review","license":"IPIP items are public domain","license_status":"methodology_review","estimated_minutes":6,"min_age":None,"retake":120,"construct":"trait"},
    {"code":"IPIP_NEWNESS_RU","title":"Как я реагирую на новое","description":"Любопытство, эксперимент и отношение к неопределённости.","source":"International Personality Item Pool","methodology":"Selected IPIP facets — exact version pending methodology review","license":"IPIP items are public domain","license_status":"methodology_review","estimated_minutes":6,"min_age":None,"retake":120,"construct":"trait"},
    {"code":"IPIP_INTERACTION_RU","title":"Как я взаимодействую","description":"Сотрудничество, доверие и ориентация на других без моральных ярлыков.","source":"International Personality Item Pool","methodology":"Selected IPIP facets — exact version pending methodology review","license":"IPIP items are public domain","license_status":"methodology_review","estimated_minutes":6,"min_age":None,"retake":120,"construct":"trait"},
    {"code":"STRENGTHS_SYNTHESIS","title":"Мои сильные стороны","description":"Синтез уже накопленных результатов, целей и наблюдений — не отдельный тест.","source":"ERA interpretation layer","methodology":"Derived profile, no independent psychological scoring","license":"Internal synthesis","license_status":"available_after_data","estimated_minutes":0,"min_age":None,"retake":30,"construct":"derived"},
]

RECOMMENDATIONS = {
    "RECOVER":{"family":"RECOVER","title":"Вернуть немного ресурса","insight":"Сейчас главный рост может быть не в новой нагрузке, а в восстановлении управляемости и энергии.","experiment":"Выбери одно необязательное дело, которое можно спокойно убрать или отложить на этой неделе."},
    "REDUCE_LOAD":{"family":"REDUCE_LOAD","title":"Снять одну лишнюю нагрузку","insight":"Высокая ответственность полезна, пока она не начинает забирать ресурс быстрее, чем он восстанавливается.","experiment":"Выбери одно необязательное обязательство и на неделю уменьши его объём или передай часть другому человеку."},
    "START_SMALL":{"family":"START_SMALL","title":"Сделать задачу меньше","insight":"Сейчас полезнее вернуть ощущение «я могу закончить», чем ставить большую цель.","experiment":"Выбери одну задачу на 20–30 минут и доведи только её до видимого результата."},
    "DECIDE_INDEPENDENTLY":{"family":"DECIDE_INDEPENDENTLY","title":"Сначала своё решение","insight":"Тебе может быть полезно чуть яснее отделить собственный выбор от ожиданий окружающих.","experiment":"В одной важной ситуации сначала запиши своё решение, а уже потом спроси мнение других."},
    "CONNECT":{"family":"CONNECT","title":"Сделать один настоящий контакт","insight":"Связь с людьми сейчас выглядит более хрупкой, чем другие части твоего состояния.","experiment":"Напиши одному человеку, с которым тебе спокойно, и предложи коротко увидеться или созвониться."},
    "SET_DIRECTION":{"family":"SET_DIRECTION","title":"Выбрать один фокус","insight":"Сейчас важнее не ускоряться, а понять, куда именно направить внимание.","experiment":"Запиши три вещи, которые занимают тебя сейчас, и выбери одну как главный фокус ближайших двух недель."},
    "FINISH_ONE":{"family":"FINISH_ONE","title":"Закрыть один открытый цикл","insight":"Один завершённый результат может дать больше ясности, чем несколько новых стартов.","experiment":"Не начинай новую небольшую идею, пока не доведёшь одну текущую до видимого результата."},
    "EXPLORE_NEW":{"family":"EXPLORE_NEW","title":"Безопасно попробовать новое","insight":"У тебя достаточно ресурса, чтобы проверить новое направление без большой ставки.","experiment":"Выбери один новый навык или формат и попробуй его один раз без обязательства продолжать."},
    "TRY_UNCERTAINTY":{"family":"TRY_UNCERTAINTY","title":"Оставить немного неизвестности","insight":"Если понятная структура даётся легко, небольшой контролируемый эксперимент может расширить выбор без большой ставки.","experiment":"Один раз выбери маленькое действие, где заранее не знаешь точный результат, и заранее ограничь его одним часом."},
    "INITIATE":{"family":"INITIATE","title":"Проявиться первым","insight":"Следующий полезный эксперимент — проверить, как меняется ситуация, когда первый шаг делаешь ты.","experiment":"Один раз сам предложи группе, другу или коллеге конкретный следующий шаг."},
    "SPEAK_UP":{"family":"SPEAK_UP","title":"Озвучить свою позицию","insight":"Иногда следующий шаг — не больше общаться, а яснее показать собственную мысль в уже существующем контакте.","experiment":"В одном разговоре сформулируй свою позицию одной прямой фразой до того, как начнёшь подстраиваться под общий тон."},
    "ASK_FOR_HELP":{"family":"ASK_FOR_HELP","title":"Попросить конкретную поддержку","insight":"Самостоятельность не исключает умение вовремя опереться на другого человека.","experiment":"Один раз попроси человека о небольшой, конкретной помощи вместо того, чтобы тянуть задачу одному."},
    "SET_BOUNDARY":{"family":"SET_BOUNDARY","title":"Поставить одну границу","insight":"Иногда ясность появляется не после нового действия, а после честного «нет».","experiment":"Откажись от одной необязательной просьбы, если она забирает ресурс у действительно важного."},
    "REQUEST_FEEDBACK":{"family":"REQUEST_FEEDBACK","title":"Получить точную обратную связь","insight":"Один внешний взгляд может помочь увидеть следующий шаг без лишних догадок.","experiment":"Попроси одного человека назвать одну твою сильную сторону и одно действие, которое сделало бы результат лучше."},
    "SIMPLIFY":{"family":"SIMPLIFY","title":"Упростить систему","insight":"Твой следующий шаг может быть не «больше стараться», а убрать лишнее из процесса.","experiment":"Выбери одну повторяющуюся задачу и сократи в ней хотя бы один ненужный шаг."},
    "STRUCTURE":{"family":"STRUCTURE","title":"Добавить одну точку структуры","insight":"Когда задач много, маленькая внешняя структура может освободить внимание вместо дополнительного контроля.","experiment":"Для одной длинной задачи запиши только три промежуточные точки и дату ближайшей, не планируя весь путь целиком."},
    "CREATE":{"family":"CREATE","title":"Создать маленький результат","insight":"Полезно перевести идею из головы в то, что можно увидеть или показать.","experiment":"Сделай маленький черновик результата: страницу, макет, видео, план или прототип."},
    "REFLECT":{"family":"REFLECT","title":"Замечать, что уже работает","insight":"Перед новым рывком полезно увидеть собственные повторяющиеся рабочие условия.","experiment":"После трёх обычных дней коротко запиши, что в каждом из них помогло тебе включиться."},
    "HELP_SOMEONE":{"family":"HELP_SOMEONE","title":"Проверить силу через вклад","insight":"Иногда сильная сторона становится понятнее, когда используется не для оценки себя, а для небольшого полезного действия.","experiment":"Помоги одному человеку с конкретной задачей, которую реально закрыть вместе за час или меньше."},
    "LEARN":{"family":"LEARN","title":"Разобраться в одном навыке","insight":"Небольшое обучение может дать больше опоры, если сразу связать его с практикой.","experiment":"Выбери один навык и потрать до часа на обучение, после чего сразу сделай маленькое практическое действие."},
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def current_month() -> str:
    return utcnow().strftime("%Y-%m")


def normalize_state_answers(answers: dict[str, Any]) -> dict[str, int]:
    state: dict[str, int] = {}
    for code in STATE_DIMENSIONS:
        value = answers.get(code)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 4:
            raise ValueError(f"invalid_{code}")
        state[code] = round(value * 25)
    return state


def vector_index(state: dict[str, int]) -> int:
    """Equal-weight display snapshot of state dimensions only; never traits."""
    return round(mean(state[code] for code in STATE_DIMENSIONS))


def state_deltas(current: dict[str, int], previous: dict[str, Any] | None) -> dict[str, int]:
    if not previous:
        return {}
    return {code: current[code] - int(previous.get(code, current[code])) for code in STATE_DIMENSIONS}


def public_checkin_answers(checkin: MonthlyCheckin) -> dict[str, int]:
    return {
        code: value
        for code, value in (checkin.answers_json or {}).items()
        if not code.startswith("_") and isinstance(value, int) and not isinstance(value, bool)
    }


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _profile_values(profile: UserVectorProfile | None) -> dict[str, Any]:
    if profile is None:
        return {"big5": {}, "self_efficacy": None, "top_interests": [], "needs": {}, "strengths": []}
    traits = dict(profile.traits_json or {})
    big5 = traits.get("big5") if isinstance(traits.get("big5"), dict) else {}
    interests = dict(profile.interests_json or {})
    needs = dict(profile.needs_json or {})
    return {
        "big5": big5,
        "self_efficacy": _number(traits.get("self_efficacy")),
        "top_interests": interests.get("top_code") if isinstance(interests.get("top_code"), list) else [],
        "needs": needs.get("basic_needs") if isinstance(needs.get("basic_needs"), dict) else {},
        "strengths": list(profile.strengths_json or []),
    }


def _append_unique(target: list[str], code: str) -> None:
    if code in QUESTION_BY_CODE and code not in target:
        target.append(code)


async def _completed_count(session: AsyncSession, user_id: int) -> int:
    return int(
        (
            await session.scalar(
                select(func.count())
                .select_from(MonthlyCheckin)
                .where(MonthlyCheckin.user_id == user_id, MonthlyCheckin.status == "completed")
            )
        )
        or 0
    )


async def _previous_completed_checkin(
    session: AsyncSession, user_id: int, month: str
) -> MonthlyCheckin | None:
    return await session.scalar(
        select(MonthlyCheckin)
        .where(
            MonthlyCheckin.user_id == user_id,
            MonthlyCheckin.status == "completed",
            MonthlyCheckin.month < month,
        )
        .order_by(desc(MonthlyCheckin.month))
    )


async def checkin_questions(
    session: AsyncSession, user_id: int, checkin: MonthlyCheckin
) -> list[dict[str, str]]:
    stored = (checkin.answers_json or {}).get("_question_codes")
    if isinstance(stored, list) and stored:
        return [QUESTION_BY_CODE[code] for code in stored if code in QUESTION_BY_CODE]

    previous = await _previous_completed_checkin(session, user_id, checkin.month)
    profile = await session.get(UserVectorProfile, user_id)
    values = _profile_values(profile)
    previous_state = dict(previous.state_json or {}) if previous else {}
    big5 = values["big5"]

    adaptive: list[str] = []
    if int(previous_state.get("energy", 100)) < 55:
        _append_unique(adaptive, "rest_guilt")
        _append_unique(adaptive, "energy_load")
    if int(previous_state.get("agency", 100)) < 55 or (values["self_efficacy"] is not None and values["self_efficacy"] < 50):
        _append_unique(adaptive, "agency_start")
        _append_unique(adaptive, "initiative_first")
    if int(previous_state.get("autonomy", 100)) < 55:
        _append_unique(adaptive, "autonomy_others")
    if int(previous_state.get("connection", 100)) < 55:
        _append_unique(adaptive, "connection_depth")
        _append_unique(adaptive, "ask_help")
    if int(previous_state.get("direction", 100)) < 55:
        _append_unique(adaptive, "direction_choice")

    conscientiousness = _number(big5.get("conscientiousness"))
    intellect = _number(big5.get("intellect"))
    extraversion = _number(big5.get("extraversion"))
    if conscientiousness is not None and conscientiousness >= 65 and int(previous_state.get("energy", 100)) < 60:
        _append_unique(adaptive, "energy_load")
    if intellect is not None and intellect >= 65 and conscientiousness is not None and conscientiousness < 55:
        _append_unique(adaptive, "finish_visibility")
    if extraversion is not None and extraversion >= 65 and int(previous_state.get("autonomy", 100)) < 60:
        _append_unique(adaptive, "autonomy_others")
    if "S" in values["top_interests"]:
        _append_unique(adaptive, "initiative_first")

    completed_count = await _completed_count(session, user_id)
    theme = THEME_QUESTIONS[min(completed_count, 11)]
    codes = [*STATE_DIMENSIONS, *adaptive[:2], theme["code"]]
    metadata = dict(checkin.answers_json or {})
    metadata["_question_codes"] = list(codes)
    metadata["_theme"] = theme["theme"]
    checkin.answers_json = metadata
    await session.flush()
    return [QUESTION_BY_CODE[code] for code in codes]


def checkin_theme(checkin: MonthlyCheckin) -> str | None:
    value = (checkin.answers_json or {}).get("_theme")
    return str(value) if value else None


def pick_recommendation(
    state: dict[str, int],
    *,
    blocked_tags: set[str] | None = None,
    previous_goal_unfinished: bool = False,
    repeated_goal_failures: int = 0,
    profile: UserVectorProfile | None = None,
    answers: dict[str, Any] | None = None,
) -> tuple[str, dict[str, str]]:
    blocked_tags = blocked_tags or set()
    answers = answers or {}
    values = _profile_values(profile)
    big5 = values["big5"]
    conscientiousness = _number(big5.get("conscientiousness"))
    intellect = _number(big5.get("intellect"))
    extraversion = _number(big5.get("extraversion"))
    self_efficacy = values["self_efficacy"]

    candidates: list[str] = []
    if state["energy"] < 40:
        candidates.append("REDUCE_LOAD" if conscientiousness is not None and conscientiousness >= 65 else "RECOVER")
    if repeated_goal_failures >= 3:
        candidates.append("START_SMALL")
    if previous_goal_unfinished and state["energy"] >= 40:
        candidates.append("START_SMALL")
    if state["agency"] < 45 or (self_efficacy is not None and self_efficacy < 45):
        candidates.append("START_SMALL")
    if intellect is not None and intellect >= 65 and conscientiousness is not None and conscientiousness < 55 and int(answers.get("finish_visibility", 4)) <= 2:
        candidates.append("FINISH_ONE")
    if extraversion is not None and extraversion >= 65 and state["autonomy"] < 55:
        candidates.append("DECIDE_INDEPENDENTLY")
    if "S" in values["top_interests"] and int(answers.get("initiative_first", 4)) <= 2 and state["energy"] >= 45:
        candidates.append("INITIATE")
    if state["autonomy"] < 45:
        candidates.append("DECIDE_INDEPENDENTLY")
    if state["connection"] < 40:
        candidates.append("CONNECT")
    if state["direction"] < 45:
        candidates.append("SET_DIRECTION")
    if min(state.values()) >= 65 and intellect is not None and intellect >= 65 and (self_efficacy is None or self_efficacy >= 60):
        candidates.extend(["EXPLORE_NEW", "CREATE", "LEARN"])
    if int(answers.get("newness_uncertainty", 4)) <= 1 and min(state.values()) >= 55:
        candidates.append("TRY_UNCERTAINTY")
    candidates.extend(["REFLECT", "REQUEST_FEEDBACK", "SIMPLIFY", "ASK_FOR_HELP", "STRUCTURE", "HELP_SOMEONE", "SPEAK_UP"])

    for tag in candidates:
        if tag not in blocked_tags:
            return tag, RECOMMENDATIONS[tag]
    for tag, recommendation in RECOMMENDATIONS.items():
        if tag not in blocked_tags:
            return tag, recommendation
    # Only reachable if a user has received every semantic family in the same
    # 90-day window. Continuing reflection is safer than inventing advice.
    return "REFLECT", RECOMMENDATIONS["REFLECT"]


async def ensure_methodology_catalog(session: AsyncSession) -> None:
    existing = set((await session.scalars(select(AssessmentDefinition.code))).all())
    for item in ASSESSMENT_CATALOG:
        if item["code"] in existing:
            continue
        session.add(
            AssessmentDefinition(
                code=item["code"],
                title=item["title"],
                description=item["description"],
                source=item["source"],
                methodology=item["methodology"],
                license=item["license"],
                license_status=item["license_status"],
                estimated_minutes=item["estimated_minutes"],
                min_age=item["min_age"],
                recommended_retake_after_days=item["retake"],
                construct_type=item["construct"],
                active=True,
            )
        )
    await session.flush()


async def has_consent(session: AsyncSession, user_id: int) -> bool:
    # The latest decision wins. A withdrawn consent must not be overridden by
    # an older accepted row.
    consent = await session.scalar(
        select(AssessmentConsent)
        .where(AssessmentConsent.user_id == user_id, AssessmentConsent.consent_version == CONSENT_VERSION)
        .order_by(desc(AssessmentConsent.created_at), desc(AssessmentConsent.id))
        .limit(1)
    )
    return bool(consent and consent.accepted)


async def record_consent(session: AsyncSession, user_id: int, accepted: bool) -> AssessmentConsent:
    row = AssessmentConsent(
        user_id=user_id,
        consent_version=CONSENT_VERSION,
        accepted=accepted,
        accepted_at=utcnow() if accepted else None,
    )
    session.add(row)
    if accepted and await session.get(AdminVisibilitySetting, user_id) is None:
        session.add(AdminVisibilitySetting(user_id=user_id))
    await session.flush()
    return row


async def get_or_create_checkin(
    session: AsyncSession, user_id: int, month: str | None = None
) -> MonthlyCheckin:
    month = month or current_month()
    row = await session.scalar(
        select(MonthlyCheckin).where(MonthlyCheckin.user_id == user_id, MonthlyCheckin.month == month)
    )
    if row is None:
        row = MonthlyCheckin(user_id=user_id, month=month, status="in_progress")
        session.add(row)
        await session.flush()
    return row


async def save_checkin(
    session: AsyncSession,
    checkin: MonthlyCheckin,
    answers: dict[str, Any],
    factors: list[str] | None = None,
    development_wants: list[str] | None = None,
) -> MonthlyCheckin:
    if checkin.status == "completed":
        raise ValueError("checkin_completed")
    questions = await checkin_questions(session, checkin.user_id, checkin)
    allowed_codes = {question["code"] for question in questions}
    merged = dict(checkin.answers_json or {})
    for code, value in answers.items():
        if code not in allowed_codes:
            raise ValueError("unknown_question")
        if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 4:
            raise ValueError("invalid_answer")
        merged[code] = value
    checkin.answers_json = merged
    if factors is not None or development_wants is not None:
        context = await session.scalar(
            select(MonthlyContext).where(MonthlyContext.checkin_id == checkin.id)
        )
        if context is None:
            context = MonthlyContext(checkin_id=checkin.id)
            session.add(context)
        if factors is not None:
            if len(factors) > 3 or any(item not in CONTEXT_OPTIONS for item in factors):
                raise ValueError("invalid_context")
            context.factors_json = list(factors)
        if development_wants is not None:
            if len(development_wants) > 3 or any(item not in DEVELOPMENT_WANTS for item in development_wants):
                raise ValueError("invalid_development_wants")
            context.development_wants_json = list(development_wants)
    await session.flush()
    return checkin


async def _unfinished_previous_goal(session: AsyncSession, user_id: int, month: str) -> bool:
    goal = await session.scalar(
        select(DevelopmentGoal)
        .where(DevelopmentGoal.user_id == user_id, DevelopmentGoal.month < month)
        .order_by(desc(DevelopmentGoal.month), desc(DevelopmentGoal.id))
    )
    if goal is None:
        return False
    review = await session.scalar(select(GoalReview).where(GoalReview.goal_id == goal.id))
    return review is not None and review.result in {"partial", "not_done"}


async def _recent_goal_failures(session: AsyncSession, user_id: int, month: str) -> int:
    goals = list(
        (
            await session.scalars(
                select(DevelopmentGoal)
                .where(DevelopmentGoal.user_id == user_id, DevelopmentGoal.month < month)
                .order_by(desc(DevelopmentGoal.month), desc(DevelopmentGoal.id))
                .limit(4)
            )
        ).all()
    )
    failures = 0
    for goal in goals:
        review = await session.scalar(select(GoalReview).where(GoalReview.goal_id == goal.id))
        if review is not None and review.result in {"partial", "not_done"}:
            failures += 1
    return failures


async def _recent_recommendation_tags(session: AsyncSession, user_id: int) -> set[str]:
    cutoff = utcnow() - timedelta(days=90)
    rows = await session.scalars(
        select(RecommendationHistory.semantic_tag).where(
            RecommendationHistory.user_id == user_id,
            RecommendationHistory.created_at >= cutoff,
        )
    )
    blocked = set(rows.all())
    rejected = await session.scalars(
        select(PersonalInsight.semantic_tag).where(
            PersonalInsight.user_id == user_id,
            PersonalInsight.accepted.is_(False),
            PersonalInsight.semantic_tag.is_not(None),
        )
    )
    blocked.update(tag for tag in rejected.all() if tag)
    return blocked


async def _baseline(session: AsyncSession, user_id: int) -> dict[str, int]:
    rows = (
        await session.scalars(
            select(MonthlyCheckin)
            .where(MonthlyCheckin.user_id == user_id, MonthlyCheckin.status == "completed")
            .order_by(desc(MonthlyCheckin.month))
            .limit(6)
        )
    ).all()
    if len(rows) < 3:
        return {}
    return {
        code: round(mean(int(row.state_json.get(code, 0)) for row in rows))
        for code in STATE_DIMENSIONS
    }


def _support_text(state: dict[str, int], profile: UserVectorProfile | None) -> str:
    highest = max(STATE_DIMENSIONS, key=lambda code: state[code])
    strengths = list(profile.strengths_json or []) if profile else []
    if strengths:
        return f"Сейчас заметной опорой выглядит {STATE_LABELS[highest].lower()}. В накопленном профиле также повторяется способность {strengths[0]}."
    return f"Сейчас наиболее устойчивой частью твоего снимка выглядит {STATE_LABELS[highest].lower()}."


def _tension_text(
    tag: str,
    state: dict[str, int],
    profile: UserVectorProfile | None,
    answers: dict[str, Any],
) -> str:
    values = _profile_values(profile)
    big5 = values["big5"]
    conscientiousness = _number(big5.get("conscientiousness"))
    intellect = _number(big5.get("intellect"))
    extraversion = _number(big5.get("extraversion"))
    if tag in {"RECOVER", "REDUCE_LOAD"} and conscientiousness is not None and conscientiousness >= 65:
        return "Ответственность и привычка доводить дела могут сейчас сталкиваться с более низким запасом энергии."
    if tag == "FINISH_ONE" and intellect is not None and intellect >= 65 and conscientiousness is not None and conscientiousness < 55:
        return "Интерес к идеям выражен сильнее, чем устойчивость доведения: новое может захватывать быстрее, чем предыдущий цикл успевает закрыться."
    if tag == "DECIDE_INDEPENDENTLY" and extraversion is not None and extraversion >= 65:
        return "Контакт с людьми даётся легче, чем сохранение собственной позиции внутри этого контакта."
    if tag == "INITIATE" and "S" in values["top_interests"] and int(answers.get("initiative_first", 4)) <= 2:
        return "Люди тебе интересны, но собственный первый шаг пока появляется реже, чем желание взаимодействовать."
    lowest = min(STATE_DIMENSIONS, key=lambda code: state[code])
    return f"Зона наибольшего напряжения сейчас — {STATE_LABELS[lowest].lower()}; это состояние, а не черта личности."


def _change_text(
    state: dict[str, int], delta: dict[str, int], baseline: dict[str, Any]
) -> str:
    if delta:
        code = max(delta, key=lambda item: abs(delta[item]))
        change = delta[code]
        if change > 0:
            return f"Сильнее всего с прошлого Check-in выросла область «{STATE_LABELS[code]}»: +{change}."
        if change < 0:
            return f"Сильнее всего с прошлого Check-in изменилась область «{STATE_LABELS[code]}»: {change}."
    if baseline:
        differences = {
            code: state[code] - int(baseline.get(code, state[code])) for code in STATE_DIMENSIONS
        }
        code = max(differences, key=lambda item: abs(differences[item]))
        diff = differences[code]
        if abs(diff) >= 8:
            return f"От твоего личного обычного уровня сильнее всего отличается «{STATE_LABELS[code]}»: {diff:+d}."
    return "Это первая или пока ещё короткая точка истории — важнее наблюдать продолжение, чем делать вывод по одному месяцу."


def _why_text(
    state: dict[str, int],
    delta: dict[str, int],
    tag: str,
    profile: UserVectorProfile | None,
    answers: dict[str, Any],
) -> str:
    tension = _tension_text(tag, state, profile, answers)
    if delta:
        lowest = min(STATE_DIMENSIONS, key=lambda code: state[code])
        change = delta.get(lowest)
        if change is not None and abs(change) >= 10:
            return f"{tension} При этом «{STATE_LABELS[lowest]}» изменилась на {change:+d} пунктов относительно прошлого месяца. Поэтому выбран один небольшой эксперимент, а не общий список советов."
    return f"{tension} Поэтому фокус выбран как проверяемый эксперимент на ближайший месяц, а не как постоянная характеристика."


async def complete_checkin(session: AsyncSession, checkin: MonthlyCheckin) -> MonthlyCheckin:
    if checkin.status == "completed":
        return checkin

    questions = await checkin_questions(session, checkin.user_id, checkin)
    answers = public_checkin_answers(checkin)
    missing = [question["code"] for question in questions if question["code"] not in answers]
    if missing:
        raise ValueError("checkin_incomplete")

    state = normalize_state_answers(answers)
    previous = await _previous_completed_checkin(session, checkin.user_id, checkin.month)
    delta = state_deltas(state, previous.state_json if previous else None)
    profile = await session.get(UserVectorProfile, checkin.user_id)
    baseline = dict(profile.baseline_json or {}) if profile else {}
    tag, recommendation = pick_recommendation(
        state,
        blocked_tags=await _recent_recommendation_tags(session, checkin.user_id),
        previous_goal_unfinished=await _unfinished_previous_goal(session, checkin.user_id, checkin.month),
        repeated_goal_failures=await _recent_goal_failures(session, checkin.user_id, checkin.month),
        profile=profile,
        answers=answers,
    )
    index = vector_index(state)
    insight = {
        "title": recommendation["title"],
        "support": _support_text(state, profile),
        "tension": _tension_text(tag, state, profile, answers),
        "change": _change_text(state, delta, baseline),
        "insight": recommendation["insight"],
        "why": _why_text(state, delta, tag, profile, answers),
        "focus": recommendation["title"],
        "experiment": recommendation["experiment"],
        "semantic_tag": tag,
        "methodology_version": STATE_METHOD_VERSION,
        "theme": checkin_theme(checkin),
        "disclaimer": "Это не диагноз и не оценка тебя как личности. Пять показателей — снимок текущего состояния; дополнительные вопросы используются только для контекста и персонализации.",
    }
    checkin.state_json = state
    checkin.index_value = index
    checkin.delta_json = delta
    checkin.insight_json = insight
    checkin.status = "completed"
    checkin.completed_at = utcnow()

    if profile is None:
        profile = UserVectorProfile(user_id=checkin.user_id)
        session.add(profile)
    profile.current_index = index
    profile.state_json = state
    profile.last_checkin_at = checkin.completed_at
    session.add(
        PersonalInsight(
            user_id=checkin.user_id,
            checkin_id=checkin.id,
            text=recommendation["insight"],
            semantic_tag=tag,
        )
    )
    session.add(
        RecommendationHistory(
            user_id=checkin.user_id,
            checkin_id=checkin.id,
            semantic_tag=tag,
            family=recommendation["family"],
            insight=recommendation["insight"],
            experiment=recommendation["experiment"],
        )
    )
    await session.flush()
    profile.baseline_json = await _baseline(session, checkin.user_id)
    # Digital-engagement points (ToR section 6): only that a checkin was
    # completed, never its answers/state/insight -- see
    # digital_engagement_service.award_vector_monthly_checkin.
    await award_vector_monthly_checkin(session, user_id=checkin.user_id, month=checkin.month)
    return checkin


async def checkin_context(session: AsyncSession, checkin_id: int) -> MonthlyContext | None:
    return await session.scalar(select(MonthlyContext).where(MonthlyContext.checkin_id == checkin_id))


async def latest_goal(session: AsyncSession, user_id: int) -> DevelopmentGoal | None:
    return await session.scalar(
        select(DevelopmentGoal)
        .where(DevelopmentGoal.user_id == user_id)
        .order_by(desc(DevelopmentGoal.month), desc(DevelopmentGoal.id))
    )


async def create_goal(
    session: AsyncSession,
    user_id: int,
    title: str,
    experiment: str | None,
    semantic_tag: str | None,
    is_custom: bool,
) -> DevelopmentGoal:
    goal = DevelopmentGoal(
        user_id=user_id,
        month=current_month(),
        title=title.strip(),
        experiment=experiment.strip() if experiment else None,
        semantic_tag=semantic_tag,
        is_custom=is_custom,
    )
    session.add(goal)
    await session.flush()
    await award_goal_set(session, user_id=user_id, goal_id=goal.id, month=goal.month)
    return goal


async def review_goal(
    session: AsyncSession,
    user_id: int,
    goal_id: int,
    result: str,
    obstacle: str | None,
    note: str | None,
) -> GoalReview:
    goal = await session.get(DevelopmentGoal, goal_id)
    if goal is None or goal.user_id != user_id:
        raise ValueError("goal_not_found")
    existing = await session.scalar(select(GoalReview).where(GoalReview.goal_id == goal_id))
    if existing is not None:
        return existing
    if result not in {"done", "partial", "not_done", "changed_mind", "lost_meaning"}:
        raise ValueError("invalid_goal_result")
    row = GoalReview(goal_id=goal_id, result=result, obstacle=obstacle, note=note)
    goal.status = "reviewed"
    session.add(row)
    await session.flush()
    if result == "done":
        await award_goal_completed(session, user_id=user_id, goal_id=goal_id, month=goal.month)
    return row


async def save_note(
    session: AsyncSession, user_id: int, checkin_id: int | None, text: str
) -> PersonalNote:
    if checkin_id is not None:
        checkin = await session.get(MonthlyCheckin, checkin_id)
        if checkin is None or checkin.user_id != user_id:
            raise ValueError("checkin_not_found")
    note = PersonalNote(user_id=user_id, checkin_id=checkin_id, text=text.strip())
    session.add(note)
    await session.flush()
    return note


async def due_personal_notes(session: AsyncSession, user_id: int) -> list[PersonalNote]:
    """Private notes that are at least 3, 6 or 12 months old.

    This endpoint is self-only. Admin development endpoints never join or
    serialize PersonalNote.
    """
    cutoff = utcnow() - timedelta(days=90)
    return list(
        (
            await session.scalars(
                select(PersonalNote)
                .where(PersonalNote.user_id == user_id, PersonalNote.created_at <= cutoff)
                .order_by(desc(PersonalNote.created_at))
                .limit(6)
            )
        ).all()
    )


async def set_insight_feedback(
    session: AsyncSession, user_id: int, insight_id: int, accepted: bool
) -> PersonalInsight:
    insight = await session.get(PersonalInsight, insight_id)
    if insight is None or insight.user_id != user_id:
        raise ValueError("insight_not_found")
    insight.accepted = accepted
    insight.hidden = not accepted
    await session.flush()
    return insight


async def save_weekly_pulse(session: AsyncSession, user_id: int, energy: int) -> WeeklyPulse:
    if energy not in {0, 1, 2}:
        raise ValueError("invalid_pulse")
    today = utcnow().date()
    week_start = today - timedelta(days=today.weekday())
    row = await session.scalar(
        select(WeeklyPulse).where(
            WeeklyPulse.user_id == user_id, WeeklyPulse.week_start == week_start
        )
    )
    if row is None:
        row = WeeklyPulse(user_id=user_id, week_start=week_start, energy=energy)
        session.add(row)
    else:
        row.energy = energy
    await session.flush()
    await award_vector_weekly_pulse(session, user_id=user_id, week_start=week_start)
    return row


async def list_history(session: AsyncSession, user_id: int) -> list[MonthlyCheckin]:
    return list(
        (
            await session.scalars(
                select(MonthlyCheckin)
                .where(
                    MonthlyCheckin.user_id == user_id,
                    MonthlyCheckin.status == "completed",
                )
                .order_by(desc(MonthlyCheckin.month))
            )
        ).all()
    )


async def visibility_settings(session: AsyncSession, user_id: int) -> AdminVisibilitySetting:
    row = await session.get(AdminVisibilitySetting, user_id)
    if row is None:
        row = AdminVisibilitySetting(user_id=user_id)
        session.add(row)
        await session.flush()
    return row


async def audit(
    session: AsyncSession,
    actor_user_id: int | None,
    action: str,
    target_user_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        DevelopmentAuditLog(
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            action=action,
            metadata_json=metadata or {},
        )
    )


# Retained for compatibility with older callers. The admin API uses the newer
# privacy-aware development_analytics service.
async def community_analytics(session: AsyncSession, period_days: int = 30) -> dict[str, Any]:
    cutoff = utcnow() - timedelta(days=max(1, min(period_days, 365)))
    completed = list(
        (
            await session.scalars(
                select(MonthlyCheckin).where(
                    MonthlyCheckin.status == "completed",
                    MonthlyCheckin.completed_at >= cutoff,
                )
            )
        ).all()
    )
    participant_count = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    User.application_status == ApplicationStatus.APPROVED,
                    User.is_archived.is_(False),
                    User.is_blocked.is_(False),
                )
            )
        )
        or 0
    )
    user_latest: dict[int, MonthlyCheckin] = {}
    for row in sorted(completed, key=lambda item: item.completed_at or utcnow(), reverse=True):
        user_latest.setdefault(row.user_id, row)
    sample = list(user_latest.values())
    n = len(sample)
    coverage = round((n / participant_count) * 100) if participant_count else 0
    if n < 5:
        return {
            "sample_size": n,
            "eligible_profiles": participant_count,
            "coverage_percent": coverage,
            "minimum_cohort": 5,
            "suppressed": True,
            "state": None,
            "message": "Недостаточно ответов для безопасной групповой аналитики.",
        }
    state = {
        code: round(mean(int(row.state_json.get(code, 0)) for row in sample))
        for code in STATE_DIMENSIONS
    }
    return {
        "sample_size": n,
        "eligible_profiles": participant_count,
        "coverage_percent": coverage,
        "minimum_cohort": 5,
        "suppressed": False,
        "state": state,
        "index": vector_index(state),
        "disclaimer": "Агрегат добровольных Check-in. Не используется для рейтинга или автоматического отбора участников.",
    }
