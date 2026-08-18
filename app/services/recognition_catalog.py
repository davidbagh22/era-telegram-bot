from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.partners import Partner, PartnerInitiative

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

OPPORTUNITY_CATEGORIES = (
    "projects",
    "events",
    "volunteering",
    "public_activity",
    "media",
    "leadership",
    "international",
)


def _category(issuer: str, title: str) -> str:
    lowered = title.lower()
    if "волонт" in lowered:
        return "volunteering"
    if "лидер" in lowered:
        return "leadership"
    if "проект" in lowered:
        return "projects"
    if "организ" in lowered or "мероприяти" in lowered:
        return "events"
    if issuer == "Дом Москвы в Ереване" and "культур" in lowered:
        return "projects"
    return "public_activity"


def _item(
    issuer: str,
    title: str,
    points: int,
    *,
    opportunity_type: str = "certificate",
    volunteer_hours: int | None = None,
) -> dict:
    eligibility: dict = {}
    if volunteer_hours is not None:
        eligibility = {"required_metrics": {"volunteer_hours": volunteer_hours}}
    return {
        "issuer": issuer,
        "title": title,
        "points": points,
        # The current approved catalog uses points as the threshold. There is
        # no rank requirement unless it is explicitly authored later.
        "rank": None,
        "eligibility": eligibility,
        "wording": title,
        "opportunity_type": opportunity_type,
        "partner_review": issuer != "ЭРА",
        "category": _category(issuer, title),
    }


ERA_ITEMS = (
    ("Активный участник ЭРА", 1500, "certificate"),
    ("За активное участие в жизни сообщества ЭРА", 1500, "certificate"),
    ("За вклад в развитие сообщества ЭРА", 2250, "certificate"),
    ("За инициативность и командную работу", 2250, "certificate"),
    ("За проектную деятельность", 3000, "certificate"),
    ("За вклад в организацию мероприятий", 3000, "certificate"),
    ("Благодарственное письмо ЭРА", 3500, "letter"),
    ("За общественную активность и инициативность", 4000, "certificate"),
    ("Организатор ЭРА", 4000, "certificate"),
    ("За лидерство и развитие команды", 5000, "certificate"),
    ("Лидер сообщества ЭРА", 5000, "certificate"),
    ("Рекомендательное письмо ЭРА", 5500, "letter"),
)

ASSOCIATION_ITEMS = (
    ("Общественная деятельность — III степень", 2500, None),
    ("Общественная деятельность — II степень", 3500, None),
    ("Общественная деятельность — I степень", 5000, None),
    ("Волонтёрская деятельность — III степень", 2500, 20),
    ("Волонтёрская деятельность — II степень", 3500, 40),
    ("Волонтёрская деятельность — I степень", 5000, 80),
    ("Развитие студенческого сообщества — III степень", 3000, None),
    ("Развитие студенческого сообщества — II степень", 4500, None),
    ("Развитие студенческого сообщества — I степень", 6000, None),
    ("За лидерство и развитие молодёжных инициатив", 7000, None),
)

MOSCOW_HOUSE_ITEMS = (
    ("За активное участие в молодёжных и культурных проектах", 3000),
    ("За вклад в реализацию общественно-культурных инициатив", 4500),
    ("Благодарственное письмо «За вклад в развитие молодёжного сотрудничества»", 6000),
)

KSOORS_ITEMS = (
    ("За активное участие в общественной жизни российских соотечественников", 3000),
    ("За вклад в развитие молодёжных инициатив", 3000),
    ("За активную общественную деятельность", 4000),
    ("За вклад в сохранение и развитие культурных связей", 4000),
    ("За проектную и организационную деятельность", 5000),
    ("За вклад в развитие молодёжного движения российских соотечественников", 5000),
    ("За вклад в развитие общественного сотрудничества", 6000),
    ("За лидерство в молодёжной общественной деятельности", 6000),
    ("За значительный вклад в развитие сообщества российских соотечественников", 7000),
    ("За особый вклад в развитие молодёжного движения российских соотечественников в Армении", 8000),
)

RECOGNITION_CATALOG = [
    *[
        _item("ЭРА", title, points, opportunity_type=opportunity_type)
        for title, points, opportunity_type in ERA_ITEMS
    ],
    *[
        _item(
            "Ассоциация студентов российских вузов в Армении",
            title,
            points,
            volunteer_hours=volunteer_hours,
        )
        for title, points, volunteer_hours in ASSOCIATION_ITEMS
    ],
    *[
        _item("Дом Москвы в Ереване", title, points)
        for title, points in MOSCOW_HOUSE_ITEMS
    ],
    *[
        _item("КСООРС Армении", title, points)
        for title, points in KSOORS_ITEMS
    ],
]

# Contract guard: 12 ЭРА + 10 association + 3 Moscow House + 10 КСООРС.
assert len(RECOGNITION_CATALOG) == 35


async def seed_recognition_catalog(session: AsyncSession) -> None:
    """Create missing recognition documents and self-heal authored fields.

    The catalog above is the approved product contract. Existing rows can
    predate that contract, so points/rank/eligibility/type are synchronized
    instead of only filling null fields. External partner opportunities are
    never touched.
    """
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
        else:
            partner.description = description
            partner.status = "issuer"
            partner.is_active = True
            partner.is_archived = False
        partners[name] = partner

    expected_titles_by_partner: dict[int, set[str]] = {
        partner.id: set() for partner in partners.values()
    }

    for item in RECOGNITION_CATALOG:
        partner = partners[item["issuer"]]
        expected_titles_by_partner[partner.id].add(item["title"])
        existing = await session.scalar(
            select(PartnerInitiative).where(
                PartnerInitiative.partner_id == partner.id,
                PartnerInitiative.title == item["title"],
            )
        )
        portfolio_type = "letter" if item["opportunity_type"] == "letter" else "certificate"
        description = (
            "Официальное признание подтверждённой деятельности. "
            "Баллы являются порогом репутации и не списываются."
        )
        if existing is None:
            existing = PartnerInitiative(
                partner_id=partner.id,
                title=item["title"],
                description=description,
                point_cost=item["points"],
                quantity=None,
                instruction="Подайте заявку после выполнения всех условий.",
                opportunity_type=item["opportunity_type"],
                min_rank=None,
                eligibility_json=item["eligibility"],
                default_award_wording=item["wording"],
                partner_review_required=item["partner_review"],
                portfolio_item_type=portfolio_type,
                category=item["category"],
                is_active=True,
                is_archived=False,
            )
            session.add(existing)
            continue

        existing.description = description
        existing.point_cost = item["points"]
        existing.quantity = None
        existing.instruction = "Подайте заявку после выполнения всех условий."
        existing.opportunity_type = item["opportunity_type"]
        existing.min_rank = None
        existing.eligibility_json = item["eligibility"]
        existing.default_award_wording = item["wording"]
        existing.partner_review_required = item["partner_review"]
        existing.portfolio_item_type = portfolio_type
        existing.category = item["category"]
        existing.is_active = True
        existing.is_archived = False

    # Hide obsolete recognition rows from these issuers so the participant
    # sees exactly the approved 35-document catalog, not historical drafts.
    for partner in partners.values():
        rows = (
            await session.scalars(
                select(PartnerInitiative).where(
                    PartnerInitiative.partner_id == partner.id,
                    PartnerInitiative.opportunity_type.in_(("certificate", "letter")),
                )
            )
        ).all()
        allowed = expected_titles_by_partner[partner.id]
        for row in rows:
            if row.title not in allowed:
                row.is_active = False
                row.is_archived = True

    await session.flush()
