from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.partners import Partner, PartnerInitiative
from app.utils.constants import ParticipationStatus

# Authored recognition catalog from the Points/Ranks/Opportunities master ToR.
# These are real application opportunities, not "coming soon" placeholders.
# Coming-soon forums/internships/delegations stay presentation-only until a
# real process exists, exactly as required by the ToR.

ISSUERS = {
    "ЭРА": "Объединение лидеров и культурных инициатив (ЭРА).",
    "Ассоциация студентов российских вузов в Армении": (
        "Партнёрская студенческая ассоциация в Армении."
    ),
    "Дом Москвы в Ереване": "Дом Москвы в Ереване.",
    "КСООРС Армении": (
        "Координационный совет общественных организаций российских "
        "соотечественников в Армении (КСООРС Армении)."
    ),
}


def _item(
    issuer: str,
    title: str,
    points: int,
    rank: str | None,
    *,
    metrics: dict[str, int] | None = None,
    any_metrics: list[dict[str, int]] | None = None,
    any_documents: list[str] | None = None,
    wording: str,
    opportunity_type: str = "certificate",
    partner_review: bool = False,
) -> dict:
    eligibility: dict = {}
    if metrics:
        eligibility["required_metrics"] = metrics
    if any_metrics:
        eligibility["required_any_metrics"] = any_metrics
    if any_documents:
        eligibility["required_any_documents"] = any_documents
    return {
        "issuer": issuer,
        "title": title,
        "points": points,
        "rank": rank,
        "eligibility": eligibility,
        "wording": wording,
        "opportunity_type": opportunity_type,
        "partner_review": partner_review,
    }


RECOGNITION_CATALOG = [
    # ЭРА — 10 certificates + two letters.
    _item(
        "ЭРА",
        "Активный участник ЭРА",
        1500,
        ParticipationStatus.ACTIVE_MEMBER,
        wording="За активное участие в жизни сообщества ЭРА и подтверждённый личный вклад.",
    ),
    _item(
        "ЭРА",
        "За активное участие в жизни сообщества ЭРА",
        1500,
        ParticipationStatus.ACTIVE_MEMBER,
        any_metrics=[{"events_attended": 3}, {"tasks_completed": 2}],
        wording="За активное участие в жизни сообщества ЭРА, инициативность и вовлечённость.",
    ),
    _item(
        "ЭРА",
        "За вклад в развитие сообщества ЭРА",
        2250,
        ParticipationStatus.ACTIVE_MEMBER,
        any_metrics=[
            {"social_activities": 2},
            {"project_activities": 3},
            {"partner_activities": 2},
        ],
        wording="За значимый вклад в развитие сообщества ЭРА и реализацию совместных инициатив.",
    ),
    _item(
        "ЭРА",
        "За инициативность и командную работу",
        2250,
        ParticipationStatus.ACTIVE_MEMBER,
        metrics={"tasks_completed": 3},
        wording="За инициативность, ответственность и результативную работу в команде ЭРА.",
    ),
    _item(
        "ЭРА",
        "За проектную деятельность",
        3000,
        ParticipationStatus.TEAM_MEMBER,
        metrics={"projects_completed": 2, "project_activities": 7},
        any_documents=[
            "Активный участник ЭРА",
            "За активное участие в жизни сообщества ЭРА",
        ],
        wording="За активную проектную деятельность, инициативность и значимый вклад в реализацию молодёжных проектов ЭРА.",
    ),
    _item(
        "ЭРА",
        "За вклад в организацию мероприятий",
        3000,
        ParticipationStatus.TEAM_MEMBER,
        any_metrics=[{"events_organized": 2}, {"events_coordinated": 1}],
        wording="За значимый вклад в подготовку и организацию мероприятий ЭРА.",
    ),
    _item(
        "ЭРА",
        "За общественную активность и инициативность",
        4000,
        ParticipationStatus.TEAM_MEMBER,
        metrics={"social_activities": 3},
        wording="За общественную активность, инициативность и вклад в социальные проекты ЭРА.",
    ),
    _item(
        "ЭРА",
        "Организатор ЭРА",
        4000,
        ParticipationStatus.PROJECT_CURATOR,
        any_metrics=[{"events_organized": 3}, {"events_coordinated": 2}],
        wording="За высокий уровень организации, координации и ответственности в проектах и мероприятиях ЭРА.",
    ),
    _item(
        "ЭРА",
        "За лидерство и развитие команды",
        5000,
        ParticipationStatus.PROJECT_CURATOR,
        metrics={"leadership_activities": 5},
        wording="За лидерство, развитие команды и устойчивый вклад в рост участников ЭРА.",
    ),
    _item(
        "ЭРА",
        "Лидер сообщества ЭРА",
        5000,
        ParticipationStatus.COMMUNITY_LEADER,
        metrics={"leadership_activities": 5, "mentorship_outcomes": 1},
        wording="За устойчивое лидерство, развитие других участников и значимый вклад в развитие сообщества ЭРА.",
    ),
    _item(
        "ЭРА",
        "Благодарственное письмо ЭРА",
        3500,
        ParticipationStatus.TEAM_MEMBER,
        any_metrics=[
            {"project_activities": 3},
            {"events_organized": 2},
            {"social_activities": 3},
        ],
        wording="За значимый личный вклад в развитие сообщества ЭРА, инициативность и участие в реализации проектов и мероприятий.",
        opportunity_type="letter",
    ),
    _item(
        "ЭРА",
        "Рекомендательное письмо ЭРА",
        5500,
        ParticipationStatus.PROJECT_CURATOR,
        any_metrics=[{"projects_led": 1}, {"leadership_activities": 5}],
        wording="Рекомендательное письмо на основании подтверждённых ролей, проектов, задач, мероприятий и результатов участника.",
        opportunity_type="letter",
    ),

    # Ассоциация студентов российских вузов в Армении.
    _item(
        "Ассоциация студентов российских вузов в Армении",
        "Общественная деятельность — III степень",
        2500,
        ParticipationStatus.ACTIVE_MEMBER,
        metrics={"social_activities": 1},
        wording="За активную общественную деятельность и участие в развитии студенческого сообщества.",
        partner_review=True,
    ),
    _item(
        "Ассоциация студентов российских вузов в Армении",
        "Общественная деятельность — II степень",
        3500,
        ParticipationStatus.TEAM_MEMBER,
        metrics={"social_activities": 3},
        wording="За значимый вклад в общественную деятельность студенческого сообщества.",
        partner_review=True,
    ),
    _item(
        "Ассоциация студентов российских вузов в Армении",
        "Общественная деятельность — I степень",
        5000,
        ParticipationStatus.PROJECT_CURATOR,
        metrics={"social_activities": 5},
        wording="За значительный и устойчивый вклад в общественную деятельность студенческого сообщества.",
        partner_review=True,
    ),
    _item(
        "Ассоциация студентов российских вузов в Армении",
        "Волонтёрство — III степень",
        2500,
        ParticipationStatus.ACTIVE_MEMBER,
        metrics={"volunteer_hours": 20},
        wording="За подтверждённую волонтёрскую деятельность и вклад в общественные инициативы.",
        partner_review=True,
    ),
    _item(
        "Ассоциация студентов российских вузов в Армении",
        "Волонтёрство — II степень",
        3500,
        ParticipationStatus.TEAM_MEMBER,
        metrics={"volunteer_hours": 40},
        wording="За значимый объём подтверждённой волонтёрской деятельности.",
        partner_review=True,
    ),
    _item(
        "Ассоциация студентов российских вузов в Армении",
        "Волонтёрство — I степень",
        5000,
        ParticipationStatus.PROJECT_CURATOR,
        metrics={"volunteer_hours": 80},
        wording="За высокий уровень и устойчивый вклад в волонтёрскую деятельность.",
        partner_review=True,
    ),
    _item(
        "Ассоциация студентов российских вузов в Армении",
        "Развитие студенческого сообщества — III степень",
        3000,
        ParticipationStatus.TEAM_MEMBER,
        metrics={"student_association_activities": 1},
        wording="За вклад в развитие студенческого сообщества российских вузов в Армении.",
        partner_review=True,
    ),
    _item(
        "Ассоциация студентов российских вузов в Армении",
        "Развитие студенческого сообщества — II степень",
        4500,
        ParticipationStatus.PROJECT_CURATOR,
        metrics={"student_association_activities": 3},
        wording="За значимый вклад в развитие студенческого сообщества российских вузов в Армении.",
        partner_review=True,
    ),
    _item(
        "Ассоциация студентов российских вузов в Армении",
        "Развитие студенческого сообщества — I степень",
        6000,
        ParticipationStatus.COMMUNITY_LEADER,
        metrics={"student_association_activities": 5},
        wording="За устойчивый вклад в развитие студенческого сообщества российских вузов в Армении.",
        partner_review=True,
    ),
    _item(
        "Ассоциация студентов российских вузов в Армении",
        "За лидерство и развитие молодёжных инициатив",
        7000,
        ParticipationStatus.COMMUNITY_LEADER,
        metrics={"leadership_activities": 5, "student_association_activities": 3},
        wording="За лидерство и значимый вклад в развитие молодёжных и студенческих инициатив.",
        partner_review=True,
    ),

    # Дом Москвы в Ереване — requires activity explicitly tagged to issuer.
    _item(
        "Дом Москвы в Ереване",
        "За активное участие в молодёжных и культурных проектах",
        3000,
        ParticipationStatus.ACTIVE_MEMBER,
        metrics={"house_moscow_activities": 1},
        wording="За активное участие в молодёжных и культурных проектах Дома Москвы в Ереване.",
        partner_review=True,
    ),
    _item(
        "Дом Москвы в Ереване",
        "За вклад в реализацию общественно-культурных инициатив",
        4500,
        ParticipationStatus.TEAM_MEMBER,
        metrics={"house_moscow_activities": 3},
        wording="За значимый вклад в реализацию общественно-культурных инициатив Дома Москвы в Ереване.",
        partner_review=True,
    ),
    _item(
        "Дом Москвы в Ереване",
        "Благодарственное письмо «За вклад в развитие молодёжного сотрудничества»",
        6000,
        ParticipationStatus.PROJECT_CURATOR,
        metrics={"house_moscow_activities": 5},
        wording="За значимый вклад в развитие молодёжного сотрудничества и реализацию совместных инициатив.",
        opportunity_type="letter",
        partner_review=True,
    ),

    # КСООРС Армении.
    _item(
        "КСООРС Армении",
        "За активное участие в общественной жизни российских соотечественников",
        3000,
        ParticipationStatus.ACTIVE_MEMBER,
        metrics={"ksoors_activities": 1},
        wording="За активное участие в общественной жизни российских соотечественников в Армении.",
        partner_review=True,
    ),
    _item(
        "КСООРС Армении",
        "За вклад в развитие молодёжных инициатив",
        3000,
        ParticipationStatus.ACTIVE_MEMBER,
        metrics={"ksoors_activities": 1, "leadership_activities": 1},
        wording="За вклад в развитие молодёжных инициатив российских соотечественников в Армении.",
        partner_review=True,
    ),
    _item(
        "КСООРС Армении",
        "За активную общественную деятельность",
        4000,
        ParticipationStatus.TEAM_MEMBER,
        metrics={"ksoors_activities": 2, "social_activities": 2},
        wording="За активную общественную деятельность в сообществе российских соотечественников.",
        partner_review=True,
    ),
    _item(
        "КСООРС Армении",
        "За вклад в сохранение и развитие культурных связей",
        4000,
        ParticipationStatus.TEAM_MEMBER,
        metrics={"ksoors_activities": 2, "culture_activities": 2},
        wording="За вклад в сохранение и развитие культурных связей российских соотечественников.",
        partner_review=True,
    ),
    _item(
        "КСООРС Армении",
        "За проектную и организационную деятельность",
        5000,
        ParticipationStatus.PROJECT_CURATOR,
        metrics={"ksoors_activities": 3, "project_activities": 5},
        wording="За результативную проектную и организационную деятельность.",
        partner_review=True,
    ),
    _item(
        "КСООРС Армении",
        "За вклад в развитие молодёжного движения российских соотечественников",
        5000,
        ParticipationStatus.PROJECT_CURATOR,
        metrics={"ksoors_activities": 3, "leadership_activities": 3},
        wording="За значимый вклад в развитие молодёжного движения российских соотечественников.",
        partner_review=True,
    ),
    _item(
        "КСООРС Армении",
        "За вклад в развитие общественного сотрудничества",
        6000,
        ParticipationStatus.PROJECT_CURATOR,
        metrics={"ksoors_activities": 4, "partner_activities": 2},
        wording="За значимый вклад в развитие общественного сотрудничества российских соотечественников.",
        partner_review=True,
    ),
    _item(
        "КСООРС Армении",
        "За лидерство в молодёжной общественной деятельности",
        6000,
        ParticipationStatus.COMMUNITY_LEADER,
        metrics={"ksoors_activities": 4, "leadership_activities": 5},
        wording="За лидерство в молодёжной общественной деятельности российских соотечественников.",
        partner_review=True,
    ),
    _item(
        "КСООРС Армении",
        "За значительный вклад в развитие сообщества российских соотечественников",
        7000,
        ParticipationStatus.COMMUNITY_LEADER,
        metrics={"ksoors_activities": 6},
        wording="За значительный и устойчивый вклад в развитие сообщества российских соотечественников в Армении.",
        partner_review=True,
    ),
    _item(
        "КСООРС Армении",
        "За особый вклад в развитие молодёжного движения российских соотечественников в Армении",
        8000,
        ParticipationStatus.COMMUNITY_LEADER,
        metrics={"ksoors_activities": 8, "leadership_activities": 5},
        wording="За особый вклад в развитие молодёжного движения российских соотечественников в Армении.",
        partner_review=True,
    ),
]


async def seed_recognition_catalog(session: AsyncSession) -> None:
    partners: dict[str, Partner] = {}
    for name, description in ISSUERS.items():
        partner = await session.scalar(select(Partner).where(Partner.name == name))
        if partner is None:
            partner = Partner(
                name=name,
                description=description,
                status="issuer",
                is_active=True,
                is_archived=False,
            )
            session.add(partner)
            await session.flush()
        partners[name] = partner

    for item in RECOGNITION_CATALOG:
        partner = partners[item["issuer"]]
        exists = await session.scalar(
            select(PartnerInitiative.id).where(
                PartnerInitiative.partner_id == partner.id,
                PartnerInitiative.title == item["title"],
            )
        )
        if exists:
            continue
        session.add(
            PartnerInitiative(
                partner_id=partner.id,
                title=item["title"],
                description=(
                    "Официальное признание подтверждённой деятельности. "
                    "Баллы являются порогом репутации и не списываются."
                ),
                point_cost=item["points"],
                quantity=None,
                instruction="Подайте заявку после выполнения всех условий.",
                opportunity_type=item["opportunity_type"],
                min_rank=item["rank"],
                eligibility_json=item["eligibility"],
                default_award_wording=item["wording"],
                partner_review_required=item["partner_review"],
                portfolio_item_type=(
                    "letter" if item["opportunity_type"] == "letter" else "certificate"
                ),
                is_active=True,
                is_archived=False,
            )
        )
    await session.flush()
