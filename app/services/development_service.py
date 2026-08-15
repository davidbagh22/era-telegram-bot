from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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
from app.utils.constants import ApplicationStatus

CONSENT_VERSION = "MY_VECTOR_V1"
STATE_METHOD_VERSION = "ERA_STATE_CORE_V1"
STATE_DIMENSIONS = ("energy", "agency", "autonomy", "connection", "direction")

STATE_LABELS = {
    "energy": "Энергия",
    "agency": "Опора",
    "autonomy": "Самостоятельность",
    "connection": "Связь",
    "direction": "Направление",
}

STATE_QUESTIONS = [
    {
        "code": "energy",
        "title": "Энергия",
        "text": "За последние две недели у меня хватало энергии на обычные дела.",
    },
    {
        "code": "agency",
        "title": "Опора",
        "text": "Когда появлялась сложная задача, я чувствовал, что могу найти первый шаг.",
    },
    {
        "code": "autonomy",
        "title": "Самостоятельность",
        "text": "В важных для меня ситуациях я чаще принимал решения, которые действительно считал своими.",
    },
    {
        "code": "connection",
        "title": "Связь",
        "text": "Я чувствовал, что рядом есть люди, с которыми могу быть собой и обратиться за поддержкой.",
    },
    {
        "code": "direction",
        "title": "Направление",
        "text": "Я понимал, на чём хочу сосредоточиться в ближайшее время.",
    },
]

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

ASSESSMENT_CATALOG = [
    {"code":"WHO5_RU","title":"Как мне сейчас?","description":"Субъективное благополучие за последние две недели.","source":"World Health Organization","methodology":"WHO-5 Well-Being Index","license":"CC BY-NC-SA 3.0; Russian wording requires approved source","license_status":"methodology_review","estimated_minutes":2,"min_age":None,"retake":14,"construct":"state"},
    {"code":"GSE_RU","title":"Насколько я верю, что справлюсь?","description":"Общая воспринимаемая самоэффективность.","source":"Schwarzer & Jerusalem","methodology":"General Self-Efficacy Scale","license":"Use only an approved Russian adaptation and documented terms","license_status":"methodology_review","estimated_minutes":4,"min_age":12,"retake":60,"construct":"state"},
    {"code":"IPIP_BIG5_RU","title":"Как я устроен?","description":"Пять широких особенностей личности без «хороших» и «плохих» типов.","source":"International Personality Item Pool","methodology":"IPIP Big Five representation — exact scale must be fixed before release","license":"IPIP items are public domain","license_status":"methodology_review","estimated_minutes":8,"min_age":None,"retake":180,"construct":"trait"},
    {"code":"ONET_RIASEC_RU","title":"Что мне действительно интересно?","description":"Шесть направлений интересов RIASEC.","source":"O*NET Resource Center","methodology":"O*NET Interest Profiler / RIASEC","license":"O*NET Career Exploration Tools license; modification rules apply","license_status":"methodology_review","estimated_minutes":7,"min_age":None,"retake":120,"construct":"interest"},
    {"code":"BPNSS_RU","title":"Чего мне сейчас не хватает?","description":"Самостоятельность, ощущение компетентности и связь с людьми.","source":"Self-Determination Theory","methodology":"Basic Psychological Need Satisfaction Scale","license":"Exact Russian adaptation and terms must be approved","license_status":"methodology_review","estimated_minutes":6,"min_age":None,"retake":45,"construct":"state"},
    {"code":"IPIP_FOLLOW_THROUGH_RU","title":"Как я начинаю и довожу","description":"Стиль действия: порядок, настойчивость, стремление к результату.","source":"International Personality Item Pool","methodology":"Selected IPIP facets — exact version pending methodology review","license":"IPIP items are public domain","license_status":"methodology_review","estimated_minutes":6,"min_age":None,"retake":120,"construct":"trait"},
    {"code":"IPIP_SOCIAL_RU","title":"Как я проявляюсь среди людей","description":"Отделяет любовь к общению от готовности проявляться первым.","source":"International Personality Item Pool","methodology":"Selected IPIP social facets — exact version pending methodology review","license":"IPIP items are public domain","license_status":"methodology_review","estimated_minutes":6,"min_age":None,"retake":120,"construct":"trait"},
    {"code":"IPIP_NEWNESS_RU","title":"Как я реагирую на новое","description":"Любопытство, эксперимент и отношение к неопределённости.","source":"International Personality Item Pool","methodology":"Selected IPIP openness facets — exact version pending methodology review","license":"IPIP items are public domain","license_status":"methodology_review","estimated_minutes":6,"min_age":None,"retake":120,"construct":"trait"},
    {"code":"IPIP_INTERACTION_RU","title":"Как я взаимодействую","description":"Сотрудничество, доверие и ориентация на других без моральных ярлыков.","source":"International Personality Item Pool","methodology":"Selected IPIP interpersonal facets — exact version pending methodology review","license":"IPIP items are public domain","license_status":"methodology_review","estimated_minutes":6,"min_age":None,"retake":120,"construct":"trait"},
    {"code":"STRENGTHS_SYNTHESIS","title":"Мои сильные стороны","description":"Синтез уже накопленных результатов, целей и наблюдений — не отдельный тест.","source":"ERA interpretation layer","methodology":"Derived profile, no independent psychological scoring","license":"Internal synthesis","license_status":"available_after_data","estimated_minutes":0,"min_age":None,"retake":30,"construct":"derived"},
]

RECOMMENDATIONS = {
    "RECOVER":{"family":"RECOVER","title":"Вернуть немного ресурса","insight":"Сейчас главный рост может быть не в новой нагрузке, а в восстановлении управляемости и энергии.","experiment":"Выбери одно необязательное дело, которое можно спокойно убрать или отложить на этой неделе."},
    "START_SMALL":{"family":"START_SMALL","title":"Сделать задачу меньше","insight":"Сейчас полезнее вернуть ощущение «я могу закончить», чем ставить большую цель.","experiment":"Выбери одну задачу на 20–30 минут и доведи только её до видимого результата."},
    "DECIDE_INDEPENDENTLY":{"family":"DECIDE_INDEPENDENTLY","title":"Сначала своё решение","insight":"Тебе может быть полезно чуть яснее отделить собственный выбор от ожиданий окружающих.","experiment":"В одной важной ситуации сначала запиши своё решение, а уже потом спроси мнение других."},
    "CONNECT":{"family":"CONNECT","title":"Сделать один настоящий контакт","insight":"Связь с людьми сейчас выглядит более хрупкой, чем другие части твоего состояния.","experiment":"Напиши одному человеку, с которым тебе спокойно, и предложи коротко увидеться или созвониться."},
    "SET_DIRECTION":{"family":"SET_DIRECTION","title":"Выбрать один фокус","insight":"Сейчас важнее не ускоряться, а понять, куда именно направить внимание.","experiment":"Запиши три вещи, которые занимают тебя сейчас, и выбери одну как главный фокус ближайших двух недель."},
    "FINISH_ONE":{"family":"FINISH_ONE","title":"Закрыть один открытый цикл","insight":"Один завершённый результат может дать больше ясности, чем несколько новых стартов.","experiment":"Не начинай новую небольшую идею, пока не доведёшь одну текущую до видимого результата."},
    "EXPLORE_NEW":{"family":"EXPLORE_NEW","title":"Безопасно попробовать новое","insight":"У тебя достаточно ресурса, чтобы проверить новое направление без большой ставки.","experiment":"Выбери один новый навык или формат и попробуй его один раз без обязательства продолжать."},
    "INITIATE":{"family":"INITIATE","title":"Проявиться первым","insight":"Следующий полезный эксперимент — проверить, как меняется ситуация, когда первый шаг делаешь ты.","experiment":"Один раз сам предложи группе, другу или коллеге конкретный следующий шаг."},
    "ASK_FOR_HELP":{"family":"ASK_FOR_HELP","title":"Попросить конкретную поддержку","insight":"Самостоятельность не исключает умение вовремя опереться на другого человека.","experiment":"Один раз попроси человека о небольшой, конкретной помощи вместо того, чтобы тянуть задачу одному."},
    "SET_BOUNDARY":{"family":"SET_BOUNDARY","title":"Поставить одну границу","insight":"Иногда ясность появляется не после нового действия, а после честного «нет».","experiment":"Откажись от одной необязательной просьбы, если она забирает ресурс у действительно важного."},
    "REQUEST_FEEDBACK":{"family":"REQUEST_FEEDBACK","title":"Получить точную обратную связь","insight":"Один внешний взгляд может помочь увидеть следующий шаг без лишних догадок.","experiment":"Попроси одного человека назвать одну твою сильную сторону и одно действие, которое сделало бы результат лучше."},
    "SIMPLIFY":{"family":"SIMPLIFY","title":"Упростить систему","insight":"Твой следующий шаг может быть не «больше стараться», а убрать лишнее из процесса.","experiment":"Выбери одну повторяющуюся задачу и сократи в ней хотя бы один ненужный шаг."},
    "CREATE":{"family":"CREATE","title":"Создать маленький результат","insight":"Полезно перевести идею из головы в то, что можно увидеть или показать.","experiment":"Сделай маленький черновик результата: страницу, макет, видео, план или прототип."},
    "REFLECT":{"family":"REFLECT","title":"Замечать, что уже работает","insight":"Перед новым рывком полезно увидеть собственные повторяющиеся рабочие условия.","experiment":"После трёх обычных дней коротко запиши, что в каждом из них помогло тебе включиться."},
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
    """Equal-weight display snapshot of state dimensions only; not a clinical index."""
    return round(mean(state[code] for code in STATE_DIMENSIONS))


def state_deltas(current: dict[str, int], previous: dict[str, Any] | None) -> dict[str, int]:
    if not previous:
        return {}
    return {code: current[code] - int(previous.get(code, current[code])) for code in STATE_DIMENSIONS}


def pick_recommendation(state: dict[str, int], *, blocked_tags: set[str] | None = None, previous_goal_unfinished: bool = False) -> tuple[str, dict[str, str]]:
    blocked_tags = blocked_tags or set()
    candidates: list[str] = []
    if state["energy"] < 40: candidates.append("RECOVER")
    if previous_goal_unfinished and state["energy"] >= 40: candidates.append("START_SMALL")
    if state["agency"] < 45: candidates.append("START_SMALL")
    if state["autonomy"] < 45: candidates.append("DECIDE_INDEPENDENTLY")
    if state["connection"] < 40: candidates.append("CONNECT")
    if state["direction"] < 45: candidates.append("SET_DIRECTION")
    if min(state.values()) >= 65: candidates.extend(["EXPLORE_NEW", "INITIATE", "CREATE", "LEARN"])
    candidates.extend(["REFLECT", "REQUEST_FEEDBACK", "SIMPLIFY", "ASK_FOR_HELP"])
    for tag in candidates:
        if tag not in blocked_tags:
            return tag, RECOMMENDATIONS[tag]
    return "REFLECT", RECOMMENDATIONS["REFLECT"]


async def ensure_methodology_catalog(session: AsyncSession) -> None:
    existing = set((await session.scalars(select(AssessmentDefinition.code))).all())
    for item in ASSESSMENT_CATALOG:
        if item["code"] in existing: continue
        session.add(AssessmentDefinition(code=item["code"], title=item["title"], description=item["description"], source=item["source"], methodology=item["methodology"], license=item["license"], license_status=item["license_status"], estimated_minutes=item["estimated_minutes"], min_age=item["min_age"], recommended_retake_after_days=item["retake"], construct_type=item["construct"], active=True))
    await session.flush()


async def has_consent(session: AsyncSession, user_id: int) -> bool:
    consent = await session.scalar(select(AssessmentConsent).where(AssessmentConsent.user_id == user_id, AssessmentConsent.consent_version == CONSENT_VERSION, AssessmentConsent.accepted.is_(True)).order_by(desc(AssessmentConsent.created_at)))
    return consent is not None


async def record_consent(session: AsyncSession, user_id: int, accepted: bool) -> AssessmentConsent:
    row = AssessmentConsent(user_id=user_id, consent_version=CONSENT_VERSION, accepted=accepted, accepted_at=utcnow() if accepted else None)
    session.add(row)
    if accepted and await session.get(AdminVisibilitySetting, user_id) is None: session.add(AdminVisibilitySetting(user_id=user_id))
    await session.flush()
    return row


async def get_or_create_checkin(session: AsyncSession, user_id: int, month: str | None = None) -> MonthlyCheckin:
    month = month or current_month()
    row = await session.scalar(select(MonthlyCheckin).where(MonthlyCheckin.user_id == user_id, MonthlyCheckin.month == month))
    if row is None:
        row = MonthlyCheckin(user_id=user_id, month=month, status="in_progress")
        session.add(row); await session.flush()
    return row


async def save_checkin(session: AsyncSession, checkin: MonthlyCheckin, answers: dict[str, Any], factors: list[str] | None = None, development_wants: list[str] | None = None) -> MonthlyCheckin:
    if checkin.status == "completed": raise ValueError("checkin_completed")
    merged = dict(checkin.answers_json or {})
    for code, value in answers.items():
        if code not in STATE_DIMENSIONS: raise ValueError("unknown_question")
        if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 4: raise ValueError("invalid_answer")
        merged[code] = value
    checkin.answers_json = merged
    if factors is not None or development_wants is not None:
        context = await session.scalar(select(MonthlyContext).where(MonthlyContext.checkin_id == checkin.id))
        if context is None: context = MonthlyContext(checkin_id=checkin.id); session.add(context)
        if factors is not None:
            if len(factors) > 3 or any(item not in CONTEXT_OPTIONS for item in factors): raise ValueError("invalid_context")
            context.factors_json = list(factors)
        if development_wants is not None:
            if len(development_wants) > 3 or any(item not in DEVELOPMENT_WANTS for item in development_wants): raise ValueError("invalid_development_wants")
            context.development_wants_json = list(development_wants)
    await session.flush(); return checkin


async def _previous_completed_checkin(session: AsyncSession, user_id: int, month: str) -> MonthlyCheckin | None:
    return await session.scalar(select(MonthlyCheckin).where(MonthlyCheckin.user_id == user_id, MonthlyCheckin.status == "completed", MonthlyCheckin.month < month).order_by(desc(MonthlyCheckin.month)))


async def _unfinished_previous_goal(session: AsyncSession, user_id: int, month: str) -> bool:
    goal = await session.scalar(select(DevelopmentGoal).where(DevelopmentGoal.user_id == user_id, DevelopmentGoal.month < month).order_by(desc(DevelopmentGoal.month), desc(DevelopmentGoal.id)))
    if goal is None: return False
    review = await session.scalar(select(GoalReview).where(GoalReview.goal_id == goal.id))
    return review is not None and review.result in {"partial", "not_done"}


async def _recent_recommendation_tags(session: AsyncSession, user_id: int) -> set[str]:
    cutoff = utcnow() - timedelta(days=90)
    rows = await session.scalars(select(RecommendationHistory.semantic_tag).where(RecommendationHistory.user_id == user_id, RecommendationHistory.created_at >= cutoff))
    return set(rows.all())


async def _baseline(session: AsyncSession, user_id: int) -> dict[str, int]:
    rows = (await session.scalars(select(MonthlyCheckin).where(MonthlyCheckin.user_id == user_id, MonthlyCheckin.status == "completed").order_by(desc(MonthlyCheckin.month)).limit(6))).all()
    if len(rows) < 3: return {}
    return {code: round(mean(int(row.state_json.get(code, 0)) for row in rows)) for code in STATE_DIMENSIONS}


async def complete_checkin(session: AsyncSession, checkin: MonthlyCheckin) -> MonthlyCheckin:
    if checkin.status == "completed": return checkin
    state = normalize_state_answers(dict(checkin.answers_json or {}))
    previous = await _previous_completed_checkin(session, checkin.user_id, checkin.month)
    delta = state_deltas(state, previous.state_json if previous else None)
    tag, recommendation = pick_recommendation(state, blocked_tags=await _recent_recommendation_tags(session, checkin.user_id), previous_goal_unfinished=await _unfinished_previous_goal(session, checkin.user_id, checkin.month))
    index = vector_index(state)
    insight = {"title":recommendation["title"],"insight":recommendation["insight"],"why":_why_text(state,delta),"focus":recommendation["title"],"experiment":recommendation["experiment"],"semantic_tag":tag,"methodology_version":STATE_METHOD_VERSION,"disclaimer":"Это не диагноз и не оценка тебя как личности. Это снимок твоего состояния по собственным рефлексивным вопросам."}
    checkin.state_json=state; checkin.index_value=index; checkin.delta_json=delta; checkin.insight_json=insight; checkin.status="completed"; checkin.completed_at=utcnow()
    profile = await session.get(UserVectorProfile, checkin.user_id)
    if profile is None: profile=UserVectorProfile(user_id=checkin.user_id); session.add(profile)
    profile.current_index=index; profile.state_json=state; profile.last_checkin_at=checkin.completed_at
    session.add(PersonalInsight(user_id=checkin.user_id, checkin_id=checkin.id, text=recommendation["insight"], semantic_tag=tag))
    session.add(RecommendationHistory(user_id=checkin.user_id, checkin_id=checkin.id, semantic_tag=tag, family=recommendation["family"], insight=recommendation["insight"], experiment=recommendation["experiment"]))
    await session.flush(); profile.baseline_json = await _baseline(session, checkin.user_id); return checkin


def _why_text(state: dict[str, int], delta: dict[str, int]) -> str:
    lowest=min(STATE_DIMENSIONS,key=lambda code:state[code]); label=STATE_LABELS[lowest].lower(); change=delta.get(lowest)
    if change is None: return f"Среди текущих областей именно {label} сейчас требует больше внимания. Поэтому мы предлагаем один небольшой эксперимент, а не общий список советов."
    if change <= -10: return f"{STATE_LABELS[lowest]} заметно ниже твоего прошлого Check-in ({change} пунктов). Поэтому фокус выбран на ближайший месяц, а не как постоянная характеристика."
    if change >= 10: return f"{STATE_LABELS[lowest]} выросла относительно прошлого Check-in (+{change}), но остаётся самой уязвимой частью текущего снимка. Есть смысл закрепить изменение одним действием."
    return f"{STATE_LABELS[lowest]} сейчас ниже остальных областей и почти не изменилась относительно прошлого Check-in. Поэтому выбран один конкретный фокус."


async def checkin_context(session: AsyncSession, checkin_id: int) -> MonthlyContext | None:
    return await session.scalar(select(MonthlyContext).where(MonthlyContext.checkin_id == checkin_id))


async def latest_goal(session: AsyncSession, user_id: int) -> DevelopmentGoal | None:
    return await session.scalar(select(DevelopmentGoal).where(DevelopmentGoal.user_id == user_id).order_by(desc(DevelopmentGoal.month), desc(DevelopmentGoal.id)))


async def create_goal(session: AsyncSession, user_id: int, title: str, experiment: str | None, semantic_tag: str | None, is_custom: bool) -> DevelopmentGoal:
    goal=DevelopmentGoal(user_id=user_id,month=current_month(),title=title.strip(),experiment=experiment.strip() if experiment else None,semantic_tag=semantic_tag,is_custom=is_custom); session.add(goal); await session.flush(); return goal


async def review_goal(session: AsyncSession, user_id: int, goal_id: int, result: str, obstacle: str | None, note: str | None) -> GoalReview:
    goal=await session.get(DevelopmentGoal,goal_id)
    if goal is None or goal.user_id != user_id: raise ValueError("goal_not_found")
    existing=await session.scalar(select(GoalReview).where(GoalReview.goal_id==goal_id))
    if existing is not None: return existing
    if result not in {"done","partial","not_done","changed_mind","lost_meaning"}: raise ValueError("invalid_goal_result")
    row=GoalReview(goal_id=goal_id,result=result,obstacle=obstacle,note=note); goal.status="reviewed"; session.add(row); await session.flush(); return row


async def save_note(session: AsyncSession, user_id: int, checkin_id: int | None, text: str) -> PersonalNote:
    if checkin_id is not None:
        checkin=await session.get(MonthlyCheckin,checkin_id)
        if checkin is None or checkin.user_id != user_id: raise ValueError("checkin_not_found")
    note=PersonalNote(user_id=user_id,checkin_id=checkin_id,text=text.strip()); session.add(note); await session.flush(); return note


async def set_insight_feedback(session: AsyncSession, user_id: int, insight_id: int, accepted: bool) -> PersonalInsight:
    insight=await session.get(PersonalInsight,insight_id)
    if insight is None or insight.user_id != user_id: raise ValueError("insight_not_found")
    insight.accepted=accepted; insight.hidden=not accepted; await session.flush(); return insight


async def save_weekly_pulse(session: AsyncSession, user_id: int, energy: int) -> WeeklyPulse:
    if energy not in {0,1,2}: raise ValueError("invalid_pulse")
    today=utcnow().date(); week_start=today-timedelta(days=today.weekday())
    row=await session.scalar(select(WeeklyPulse).where(WeeklyPulse.user_id==user_id,WeeklyPulse.week_start==week_start))
    if row is None: row=WeeklyPulse(user_id=user_id,week_start=week_start,energy=energy); session.add(row)
    else: row.energy=energy
    await session.flush(); return row


async def list_history(session: AsyncSession, user_id: int) -> list[MonthlyCheckin]:
    return list((await session.scalars(select(MonthlyCheckin).where(MonthlyCheckin.user_id==user_id,MonthlyCheckin.status=="completed").order_by(desc(MonthlyCheckin.month)))).all())


async def visibility_settings(session: AsyncSession, user_id: int) -> AdminVisibilitySetting:
    row=await session.get(AdminVisibilitySetting,user_id)
    if row is None: row=AdminVisibilitySetting(user_id=user_id); session.add(row); await session.flush()
    return row


async def audit(session: AsyncSession, actor_user_id: int | None, action: str, target_user_id: int | None = None, metadata: dict[str, Any] | None = None) -> None:
    session.add(DevelopmentAuditLog(actor_user_id=actor_user_id,target_user_id=target_user_id,action=action,metadata_json=metadata or {}))


async def community_analytics(session: AsyncSession, period_days: int = 30) -> dict[str, Any]:
    cutoff=utcnow()-timedelta(days=max(1,min(period_days,365)))
    completed=list((await session.scalars(select(MonthlyCheckin).where(MonthlyCheckin.status=="completed",MonthlyCheckin.completed_at>=cutoff))).all())
    participant_count=int((await session.scalar(select(func.count()).select_from(User).where(User.application_status==ApplicationStatus.APPROVED,User.is_archived.is_(False),User.is_blocked.is_(False)))) or 0)
    user_latest:dict[int,MonthlyCheckin]={}
    for row in sorted(completed,key=lambda item:item.completed_at or utcnow(),reverse=True): user_latest.setdefault(row.user_id,row)
    sample=list(user_latest.values()); n=len(sample); coverage=round((n/participant_count)*100) if participant_count else 0
    if n < 5: return {"sample_size":n,"eligible_profiles":participant_count,"coverage_percent":coverage,"minimum_cohort":5,"suppressed":True,"state":None,"message":"Недостаточно ответов для безопасной групповой аналитики."}
    state={code:round(mean(int(row.state_json.get(code,0)) for row in sample)) for code in STATE_DIMENSIONS}
    return {"sample_size":n,"eligible_profiles":participant_count,"coverage_percent":coverage,"minimum_cohort":5,"suppressed":False,"state":state,"index":vector_index(state),"disclaimer":"Агрегат добровольных Check-in. Не используется для рейтинга или автоматического отбора участников."}
