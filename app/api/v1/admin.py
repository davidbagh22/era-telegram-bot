from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.rate_limit import enforce_rate_limit
from app.config import Settings
from app.database.models import (
    Auction,
    Badge,
    DataDeletionRequest,
    Event,
    EventActivitySubmission,
    EventRegistration,
    Office,
    Project,
    RewardItem,
    RewardRedemption,
    Task,
    TaskSubmission,
    User,
    UserOffice,
)
from app.database.management_models import AdminSurvey
from app.database.partners import Partner, PartnerInitiative, PartnerOfferApplication
from app.keyboards.participant import main_inline_keyboard, open_app_button
from app.services import (
    auction_service,
    data_rights_service,
    event_activity_service,
    event_moderation_service,
    event_registration_service,
    office_management_service,
    opportunity_service,
    project_workflow_service,
    redemption_service,
    survey_admin_service,
    survey_service,
    task_review_service,
    user_management_service,
)
from app.services.admin_analytics_service import EXCEL_SECTION_MAP, build_analytics_payload
from app.services.admin_broadcast_service import (
    BroadcastError,
    department_options,
    direction_options,
    preview_recipient_count,
    send_chat_broadcast,
    send_personal_broadcast,
)
from app.services.admin_contacts_service import ContactError
from app.services.admin_contacts_service import archive_contact as archive_org_contact
from app.services.admin_contacts_service import create_contact as create_org_contact
from app.services.admin_contacts_service import list_contacts as list_org_contacts
from app.services.admin_activity_feed_service import recent_activity
from app.services.admin_dashboard_service import dashboard_metrics, has_dashboard_access
from app.services.admin_goals_service import GoalError, create_goal, decide_goal, goal_out, list_goals
from app.services.admin_greetings_service import (
    GreetingError,
    list_greetings,
    toggle_greeting,
    update_greeting_text,
)
from app.services.admin_structure_service import StructureError, list_departments, update_department_description
from app.services.application_review_service import (
    approve_application,
    reject_application,
    request_more_info,
)
from app.services.authorization_service import (
    active_permissions,
    can_manage_events,
    can_manage_partners,
    can_manage_people,
    can_manage_permissions,
    can_manage_tasks,
    can_view_people,
    is_full_admin,
)
from app.services.audit_service import audit
from app.services.chat_access_service import sync_user_chat_access
from app.services.chat_registry_service import check_chats_health, list_chat_registry
from app.services.excel_service import build_analytics_workbook
from app.services.maintenance_service import (
    CONFIRMATION_PHRASE,
    COUNT_LABELS,
    reset_operational_data,
    reset_preview,
)
from app.services.notification_service import broadcast_detailed, safe_send
from app.services.points_service import total_points
from app.services.project_workspace_service import can_review_projects
from app.utils import texts
from app.utils.constants import PERMISSIONS, PRIVILEGED_ROLES, ROLE_LABELS, ApplicationStatus
from app.utils.constants import Role as RoleEnum
from app.utils.deep_links import miniapp_event_url, miniapp_opportunity_url, miniapp_task_url

router = APIRouter(prefix="/admin", tags=["admin"])

# Blunt defense against a stolen/leaked admin token being used to hammer
# decide-endpoints (approve/reject/moderate) — see
# docs/PRODUCTION_READINESS_AUDIT.md finding #11. Shared across all decide
# actions in this router (not per-endpoint) so rotating between them
# doesn't reset the budget. Generous enough that no real admin reviewing a
# queue by hand would ever hit it.
ADMIN_ACTION_RATE_LIMIT = 30
ADMIN_ACTION_RATE_LIMIT_WINDOW_SECONDS = 60


async def enforce_admin_action_rate_limit(request: Request) -> None:
    await enforce_rate_limit(
        request,
        key_prefix="admin_action",
        limit=ADMIN_ACTION_RATE_LIMIT,
        window_seconds=ADMIN_ACTION_RATE_LIMIT_WINDOW_SECONDS,
    )


async def require_dashboard_access(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not has_dashboard_access(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="admin_access_required")
    return user


class DashboardOut(BaseModel):
    metrics: dict[str, int]
    attention_total: int


@router.get("/dashboard", response_model=DashboardOut)
async def read_dashboard(
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> DashboardOut:
    metrics = await dashboard_metrics(session)
    return DashboardOut(metrics=metrics.values, attention_total=metrics.attention_total)


class ActivityEntryOut(BaseModel):
    id: int
    actor_name: str | None
    summary: str
    entity_type: str
    created_at: str


@router.get("/recent-activity", response_model=list[ActivityEntryOut])
async def read_recent_activity(
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> list[ActivityEntryOut]:
    entries = await recent_activity(session)
    return [
        ActivityEntryOut(
            id=e.id, actor_name=e.actor_name, summary=e.summary,
            entity_type=e.entity_type, created_at=e.created_at.isoformat(),
        )
        for e in entries
    ]


# ---------------------------------------------------------------------------
# Analytics / Excel export — the Mini App equivalent of the bot's
# "📊 Аналитика и Excel" flow (app/handlers/admin/management_ready.py).
# Both now share app/services/admin_analytics_service.py so the numbers
# never drift between the two surfaces.
# ---------------------------------------------------------------------------


class AnalyticsSummaryOut(BaseModel):
    total_users: int
    approved_users: int
    pending_users: int
    events: int
    projects: int
    contacts: int
    goals: int


@router.get("/analytics", response_model=AnalyticsSummaryOut)
async def read_analytics_summary(
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> AnalyticsSummaryOut:
    data = await build_analytics_payload(session)
    return AnalyticsSummaryOut(**data.summary)


@router.get("/analytics/export.xlsx")
async def export_analytics_excel(
    section: Literal["all", "users", "departments", "events", "projects"] = "all",
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> Response:
    data = await build_analytics_payload(session)
    content = build_analytics_workbook(
        data.users,
        data.events,
        data.projects,
        data.totals,
        department_stats=data.department_stats,
        direction_stats=data.direction_stats,
        goals=data.goals,
        contacts=data.contacts,
        sections=EXCEL_SECTION_MAP.get(section),
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="ERA_analytics_{section}.xlsx"'},
    )


# ---------------------------------------------------------------------------
# Admin tools — monthly goals, organization contacts, department structure,
# and chat greetings. Mini App equivalents of the bot's "🎯 Ежемесячные
# цели", "🤝 База организаций", "🏛 Редактор структуры" and "👋 Автоматические
# приветствия" flows (app/handlers/admin/management_ready.py,
# app/handlers/admin/panel.py). Each shares its logic with the bot handler
# via app/services/admin_*_service.py so the two surfaces can't drift before
# the bot's /panel tree is retired.
# ---------------------------------------------------------------------------


class GoalOut(BaseModel):
    id: int
    month: str
    title: str
    target_value: int
    current_value: int
    status: str
    scope_type: str
    scope_name: str | None


class GoalCreateIn(BaseModel):
    title: str
    target_value: int
    month: str | None = None
    scope_query: str | None = None


@router.get("/goals", response_model=list[GoalOut])
async def read_goals(
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> list[GoalOut]:
    return [GoalOut(**asdict(goal)) for goal in await list_goals(session)]


@router.post("/goals", response_model=GoalOut)
async def create_new_goal(
    payload: GoalCreateIn,
    admin: User = Depends(require_dashboard_access),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> GoalOut:
    try:
        goal = await create_goal(
            session,
            title=payload.title,
            target_value=payload.target_value,
            month=payload.month,
            scope_query=payload.scope_query,
            timezone=settings.timezone,
            updated_by=admin.id,
        )
    except GoalError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    return GoalOut(**asdict(await goal_out(session, goal)))


@router.post("/goals/{goal_id}/{action}", response_model=GoalOut)
async def decide_goal_endpoint(
    goal_id: int,
    action: Literal["inc", "done", "delete"],
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> GoalOut:
    try:
        goal = await decide_goal(session, goal_id, action, admin.id)
    except GoalError as exc:
        code = 404 if exc.code == "goal_not_found" else 422
        raise HTTPException(status_code=code, detail=exc.code) from exc
    return GoalOut(**asdict(await goal_out(session, goal)))


class ContactOut(BaseModel):
    id: int
    organization_name: str
    contact_name: str | None
    position: str | None
    second_contact_name: str | None
    second_position: str | None
    email: str | None
    phone: str | None
    notes: str | None


class ContactCreateIn(BaseModel):
    organization_name: str
    contact_name: str | None = None
    position: str | None = None
    second_contact_name: str | None = None
    second_position: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None


@router.get("/organization-contacts", response_model=list[ContactOut])
async def read_org_contacts(
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> list[ContactOut]:
    return [ContactOut(**asdict(contact)) for contact in await list_org_contacts(session)]


@router.post("/organization-contacts", response_model=ContactOut)
async def create_new_org_contact(
    payload: ContactCreateIn,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> ContactOut:
    try:
        contact = await create_org_contact(session, **payload.model_dump(), created_by=admin.id)
    except ContactError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    return ContactOut(
        id=contact.id, organization_name=contact.organization_name, contact_name=contact.contact_name,
        position=contact.position, second_contact_name=contact.second_contact_name,
        second_position=contact.second_position, email=contact.email, phone=contact.phone,
        notes=contact.notes,
    )


@router.post("/organization-contacts/{contact_id}/archive", response_model=ContactOut)
async def archive_org_contact_endpoint(
    contact_id: int,
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> ContactOut:
    try:
        contact = await archive_org_contact(session, contact_id)
    except ContactError as exc:
        raise HTTPException(status_code=404, detail=exc.code) from exc
    return ContactOut(
        id=contact.id, organization_name=contact.organization_name, contact_name=contact.contact_name,
        position=contact.position, second_contact_name=contact.second_contact_name,
        second_position=contact.second_position, email=contact.email, phone=contact.phone,
        notes=contact.notes,
    )


class DepartmentStructureOut(BaseModel):
    id: int
    name: str
    description: str | None


class DepartmentDescriptionIn(BaseModel):
    description: str


@router.get("/departments/structure", response_model=list[DepartmentStructureOut])
async def read_department_structure(
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> list[DepartmentStructureOut]:
    return [DepartmentStructureOut(**asdict(d)) for d in await list_departments(session)]


@router.patch("/departments/{department_id}/description", response_model=DepartmentStructureOut)
async def update_department_description_endpoint(
    department_id: int,
    payload: DepartmentDescriptionIn,
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> DepartmentStructureOut:
    try:
        department = await update_department_description(session, department_id, payload.description)
    except StructureError as exc:
        raise HTTPException(status_code=404, detail=exc.code) from exc
    return DepartmentStructureOut(id=department.id, name=department.name, description=department.description)


class ChatGreetingOut(BaseModel):
    id: int
    chat_key: str
    title: str
    text: str
    is_enabled: bool
    is_bound: bool


class ChatGreetingTextIn(BaseModel):
    text: str


@router.get("/chat-greetings", response_model=list[ChatGreetingOut])
async def read_chat_greetings(
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> list[ChatGreetingOut]:
    return [ChatGreetingOut(**asdict(g)) for g in await list_greetings(session)]


@router.patch("/chat-greetings/{greeting_id}/text", response_model=ChatGreetingOut)
async def update_chat_greeting_text(
    greeting_id: int,
    payload: ChatGreetingTextIn,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> ChatGreetingOut:
    try:
        item = await update_greeting_text(session, greeting_id, payload.text, admin.id)
    except GreetingError as exc:
        code = 404 if exc.code == "greeting_not_found" else 422
        raise HTTPException(status_code=code, detail=exc.code) from exc
    return ChatGreetingOut(
        id=item.id, chat_key=item.chat_key, title=item.title, text=item.text,
        is_enabled=item.is_enabled, is_bound=item.chat_id is not None,
    )


@router.post("/chat-greetings/{greeting_id}/toggle", response_model=ChatGreetingOut)
async def toggle_chat_greeting(
    greeting_id: int,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> ChatGreetingOut:
    try:
        item = await toggle_greeting(session, greeting_id, admin.id)
    except GreetingError as exc:
        raise HTTPException(status_code=404, detail=exc.code) from exc
    return ChatGreetingOut(
        id=item.id, chat_key=item.chat_key, title=item.title, text=item.text,
        is_enabled=item.is_enabled, is_bound=item.chat_id is not None,
    )


# ---------------------------------------------------------------------------
# Broadcasts — personal-message and chat broadcast. Mini App equivalents of
# the bot's "📨 Рассылка в личные сообщения" and "📣 Сообщение в выбранные
# чаты" flows — see app/services/admin_broadcast_service.py. Chat binding
# itself stays bot-only (see that module's docstring); this only sends to
# chats already bound via /bind.
# ---------------------------------------------------------------------------


class AudienceOptionOut(BaseModel):
    value: str
    label: str


class BroadcastAudienceOptionsOut(BaseModel):
    roles: list[AudienceOptionOut]
    departments: list[AudienceOptionOut]
    directions: list[AudienceOptionOut]
    ages: list[AudienceOptionOut]


_ROLE_LABELS = {
    "participant": "Участники",
    "activist": "Активисты",
    "leader": "Лидеры",
    "head": "Руководители",
    "council": "Совет",
}
_AGE_LABELS = {
    "14_17": "14–17",
    "18_24": "18–24",
    "25_34": "25–34",
    "35_plus": "35+",
}


@router.get("/broadcast/audience-options", response_model=BroadcastAudienceOptionsOut)
async def read_broadcast_audience_options(
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> BroadcastAudienceOptionsOut:
    return BroadcastAudienceOptionsOut(
        roles=[AudienceOptionOut(value=value, label=label) for value, label in _ROLE_LABELS.items()],
        departments=[AudienceOptionOut(value=o.value, label=o.label) for o in await department_options(session)],
        directions=[AudienceOptionOut(value=o.value, label=o.label) for o in await direction_options(session)],
        ages=[AudienceOptionOut(value=value, label=label) for value, label in _AGE_LABELS.items()],
    )


class BroadcastPreviewCountOut(BaseModel):
    count: int


@router.get("/broadcast/preview-count", response_model=BroadcastPreviewCountOut)
async def read_broadcast_preview_count(
    audience: Literal["all", "role", "department", "direction", "age", "city"],
    filter_value: str | None = None,
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> BroadcastPreviewCountOut:
    # Lets the composer show "Получателей: N" before the admin commits to
    # sending -- read-only DB count, no Telegram call, so unlike the actual
    # send endpoints below this isn't rate-limited (same reasoning as
    # /broadcast/audience-options just above). 2026-08 master spec section 33.
    try:
        count = await preview_recipient_count(session, audience, filter_value)
    except BroadcastError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    return BroadcastPreviewCountOut(count=count)


class PersonalBroadcastIn(BaseModel):
    audience: Literal["all", "role", "department", "direction", "age", "city"]
    filter_value: str | None = None
    text: str


class PersonalBroadcastResultOut(BaseModel):
    total: int
    sent: int
    failed: int
    duplicates: int
    temporary_failed: int
    permanent_failed: int


@router.post("/broadcast", response_model=PersonalBroadcastResultOut)
async def send_broadcast(
    payload: PersonalBroadcastIn,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> PersonalBroadcastResultOut:
    if bot is None:
        raise HTTPException(status_code=503, detail="bot_unavailable")
    try:
        result = await send_personal_broadcast(
            bot, session, audience=payload.audience, filter_value=payload.filter_value,
            text=payload.text, author_id=admin.id,
        )
    except BroadcastError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    return PersonalBroadcastResultOut(
        total=result.total, sent=result.sent, failed=result.failed, duplicates=result.duplicates,
        temporary_failed=result.temporary_failed, permanent_failed=result.permanent_failed,
    )


class ChatBroadcastIn(BaseModel):
    chat_key: Literal["general", "internal", "external", "leaders"]
    text: str


@router.post("/broadcast/chat")
async def send_chat_broadcast_endpoint(
    payload: ChatBroadcastIn,
    admin: User = Depends(require_dashboard_access),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> dict[str, bool]:
    if bot is None:
        raise HTTPException(status_code=503, detail="bot_unavailable")
    try:
        await send_chat_broadcast(bot, settings, session, chat_key=payload.chat_key, text=payload.text, actor_id=admin.id)
    except BroadcastError as exc:
        if exc.code == "delivery_failed":
            # send_chat_broadcast() already staged a chat.broadcast_failed
            # audit row for the Chat Registry's "last error" column before
            # raising -- commit it now, or get_session's request-scope
            # rollback (triggered by the HTTPException below) would erase
            # it along with everything else in this failed request.
            await session.commit()
        code = 404 if exc.code == "chat_not_bound" else 422
        raise HTTPException(status_code=code, detail=exc.code) from exc
    return {"ok": True}


# ---------------------------------------------------------------------------
# Chat Infrastructure Registry (2026-08 master spec section 30) -- one
# screen for the 4 org chats' binding/permissions/greeting state and
# recent send history, plus a read-only-until-pressed Telegram health
# check. See app/services/chat_registry_service.py.
class ChatRegistryOut(BaseModel):
    chat_key: str
    title: str
    chat_id: int | None
    is_bound: bool
    permission_description: str
    greeting_enabled: bool | None
    last_sent_at: datetime | None
    last_error_at: datetime | None


@router.get("/chats", response_model=list[ChatRegistryOut])
async def read_chat_registry(
    _admin: User = Depends(require_dashboard_access),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> list[ChatRegistryOut]:
    return [ChatRegistryOut(**entry.__dict__) for entry in await list_chat_registry(session, settings)]


class ChatHealthOut(BaseModel):
    chat_key: str
    ok: bool
    detail: str


@router.post("/chats/health-check", response_model=list[ChatHealthOut])
async def run_chats_health_check(
    admin: User = Depends(require_dashboard_access),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> list[ChatHealthOut]:
    if bot is None:
        raise HTTPException(status_code=503, detail="bot_unavailable")
    results = await check_chats_health(bot, settings)
    await audit(
        session,
        actor_id=admin.id,
        action="chats.health_check_run",
        entity_type="chat",
        entity_id=None,
        new_value={"results": {r.chat_key: r.ok for r in results}},
    )
    return [ChatHealthOut(chat_key=r.chat_key, ok=r.ok, detail=r.detail) for r in results]


class ApplicationOut(BaseModel):
    id: int
    telegram_id: int
    first_name: str
    last_name: str | None
    city: str | None
    occupation: str | None
    motivation: str | None
    application_status: str
    created_at: str


def _to_application_out(user: User) -> ApplicationOut:
    return ApplicationOut(
        id=user.id,
        telegram_id=user.telegram_id,
        first_name=user.first_name,
        last_name=user.last_name,
        city=user.city,
        occupation=user.occupation,
        motivation=user.motivation,
        application_status=user.application_status,
        created_at=user.created_at.isoformat(),
    )


@router.get("/applications", response_model=list[ApplicationOut])
async def read_applications(
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> list[ApplicationOut]:
    rows = await session.scalars(
        select(User)
        .where(
            User.application_status.in_([ApplicationStatus.PENDING, ApplicationStatus.NEEDS_INFO]),
            User.is_archived.is_(False),
        )
        .order_by(User.created_at)
    )
    return [_to_application_out(u) for u in rows.all()]


class CommentIn(BaseModel):
    comment: str = ""


@router.post("/applications/{user_id}/approve", response_model=ApplicationOut)
async def approve_user_application(
    user_id: int,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> ApplicationOut:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    result = await approve_application(session, target, actor_id=admin.id)
    if not result.changed:
        raise HTTPException(status_code=409, detail=result.code)
    if bot is not None:
        # Mirrors app/handlers/admin/panel.py::approve_user exactly, so a
        # Mini App approval looks identical to the Bot one to the user.
        await safe_send(
            bot,
            target.telegram_id,
            texts.APPLICATION_APPROVED,
            main_inline_keyboard(miniapp_url=settings.effective_miniapp_url),
        )
        await safe_send(
            bot, target.telegram_id, "Перед стартом — короткие правила сообщества\n\n" + texts.CHAT_RULES
        )
        await sync_user_chat_access(bot, settings, session, target)
    return _to_application_out(target)


@router.post("/applications/{user_id}/reject", response_model=ApplicationOut)
async def reject_user_application(
    user_id: int,
    payload: CommentIn,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> ApplicationOut:
    if not payload.comment.strip():
        raise HTTPException(status_code=422, detail="comment_required")
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    result = await reject_application(session, target, actor_id=admin.id, comment=payload.comment)
    if not result.changed:
        raise HTTPException(status_code=409, detail=result.code)
    if bot is not None:
        await safe_send(
            bot,
            target.telegram_id,
            f"{texts.APPLICATION_REJECTED}\n\nКомментарий: {payload.comment}",
        )
    return _to_application_out(target)


@router.post("/applications/{user_id}/request-info", response_model=ApplicationOut)
async def request_more_info_endpoint(
    user_id: int,
    payload: CommentIn,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> ApplicationOut:
    if not payload.comment.strip():
        raise HTTPException(status_code=422, detail="comment_required")
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    result = await request_more_info(session, target, actor_id=admin.id, comment=payload.comment)
    if not result.changed:
        raise HTTPException(status_code=409, detail=result.code)
    if bot is not None:
        await safe_send(bot, target.telegram_id, texts.APPLICATION_NEEDS_INFO.format(comment=payload.comment))
    return _to_application_out(target)


class ProjectModerationOut(BaseModel):
    id: int
    title: str
    short_description: str
    status: str
    author_id: int
    submitted_at: str | None
    admin_comment: str | None


def _to_moderation_out(project: Project) -> ProjectModerationOut:
    return ProjectModerationOut(
        id=project.id,
        title=project.title,
        short_description=project.short_description,
        status=project.status,
        author_id=project.author_id,
        submitted_at=project.submitted_at.isoformat() if project.submitted_at else None,
        admin_comment=project.admin_comment,
    )


async def require_project_reviewer(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not await can_review_projects(session, user, settings):
        raise HTTPException(status_code=403, detail="reviewer_access_required")
    return user


@router.get("/projects", response_model=list[ProjectModerationOut])
async def read_projects_for_review(
    _reviewer: User = Depends(require_project_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[ProjectModerationOut]:
    projects = await project_workflow_service.list_projects_for_review(session)
    return [_to_moderation_out(project) for project in projects]


class ProjectDecisionIn(BaseModel):
    action: str
    comment: str


@router.post("/projects/{project_id}/decide", response_model=ProjectModerationOut)
async def decide_project_endpoint(
    project_id: int,
    payload: ProjectDecisionIn,
    reviewer: User = Depends(require_project_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> ProjectModerationOut:
    if not payload.comment.strip():
        raise HTTPException(status_code=422, detail="comment_required")
    if payload.action not in project_workflow_service.PROJECT_DECISION_ACTIONS:
        raise HTTPException(status_code=422, detail="invalid_action")
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    result = await project_workflow_service.decide_project(
        session, project, action=payload.action, comment=payload.comment, actor=reviewer
    )
    if bot is not None:
        author = await session.get(User, project.author_id)
        if author is not None:
            await safe_send(
                bot,
                author.telegram_id,
                f"💡 {result.notice}\n\nПроект: {project.title}\n\nКомментарий команды ЭРА:\n{payload.comment}",
            )
    return _to_moderation_out(project)


# "Looking for a team" post moderation — approve/edit/reject/publish, the
# Mini App equivalent of app/handlers/admin/projects_block5_team.py.
# Distinct from ProjectWorkspace's in-app roles/applications (PR5): this
# broadcasts to the general Telegram chat, reaching people who aren't
# necessarily browsing the Mini App.


class TeamPostOut(BaseModel):
    project_id: int
    project_title: str
    author_name: str
    text: str
    status: str


async def _to_team_post_out(session: AsyncSession, project: Project) -> TeamPostOut:
    state = project_workflow_service.team_post_state(project)
    author = await session.get(User, project.author_id)
    return TeamPostOut(
        project_id=project.id,
        project_title=project.title,
        author_name=f"{author.first_name} {author.last_name or ''}".strip() if author else "—",
        text=state.text if state else "",
        status=state.status if state else "",
    )


@router.get("/projects/team-posts", response_model=list[TeamPostOut])
async def read_pending_team_posts(
    _reviewer: User = Depends(require_project_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[TeamPostOut]:
    projects = await project_workflow_service.list_projects_with_pending_team_post(session)
    return [await _to_team_post_out(session, project) for project in projects]


@router.post("/projects/{project_id}/team-post/prepare", response_model=TeamPostOut)
async def prepare_team_post_endpoint(
    project_id: int,
    _reviewer: User = Depends(require_project_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> TeamPostOut:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    if not project_workflow_service.prepare_team_post(project):
        raise HTTPException(status_code=409, detail="no_team_post")
    return await _to_team_post_out(session, project)


class TeamPostEditIn(BaseModel):
    text: str


@router.post("/projects/{project_id}/team-post/edit", response_model=TeamPostOut)
async def edit_team_post_endpoint(
    project_id: int,
    payload: TeamPostEditIn,
    _reviewer: User = Depends(require_project_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> TeamPostOut:
    text = payload.text.strip()
    if len(text) < 30:
        raise HTTPException(status_code=422, detail="text_too_short")
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    if not project_workflow_service.edit_team_post(project, text):
        raise HTTPException(status_code=409, detail="no_team_post")
    return await _to_team_post_out(session, project)


@router.post("/projects/{project_id}/team-post/reject", response_model=TeamPostOut)
async def reject_team_post_endpoint(
    project_id: int,
    _reviewer: User = Depends(require_project_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> TeamPostOut:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    if not project_workflow_service.reject_team_post(project):
        raise HTTPException(status_code=409, detail="no_team_post")
    if bot is not None:
        author = await session.get(User, project.author_id)
        if author is not None:
            await safe_send(
                bot,
                author.telegram_id,
                f"Публикация для поиска команды по проекту «{project.title}» отклонена.",
            )
    return await _to_team_post_out(session, project)


@router.post("/projects/{project_id}/team-post/publish", response_model=TeamPostOut)
async def publish_team_post_endpoint(
    project_id: int,
    _reviewer: User = Depends(require_project_reviewer),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> TeamPostOut:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    text = project_workflow_service.publish_team_post(project)
    if text is None:
        raise HTTPException(status_code=409, detail="not_prepared")
    if bot is not None:
        if settings.general_chat_id:
            await safe_send(bot, settings.general_chat_id, f"Команда для проекта ЭРА\n\n{project.title}\n\n{text}")
        author = await session.get(User, project.author_id)
        if author is not None:
            await safe_send(
                bot,
                author.telegram_id,
                f"Публикация для поиска команды по проекту «{project.title}» одобрена.",
            )
    return await _to_team_post_out(session, project)


class EventModerationOut(BaseModel):
    id: int
    title: str
    description: str
    event_date: str
    event_time: str
    location: str
    status: str


def _to_event_moderation_out(event: Event) -> EventModerationOut:
    return EventModerationOut(
        id=event.id,
        title=event.title,
        description=event.description,
        event_date=event.event_date.isoformat(),
        event_time=event.event_time.isoformat(),
        location=event.location,
        status=event.status,
    )


async def require_event_reviewer(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_events(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="event_reviewer_access_required")
    return user


@router.get("/events", response_model=list[EventModerationOut])
async def read_events_for_review(
    _reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[EventModerationOut]:
    events = await event_moderation_service.list_events_for_review(session)
    return [_to_event_moderation_out(event) for event in events]


class EventDecisionIn(BaseModel):
    action: str
    comment: str = ""


@router.post("/events/{event_id}/decide", response_model=EventModerationOut)
async def decide_event_endpoint(
    event_id: int,
    payload: EventDecisionIn,
    reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> EventModerationOut:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    if payload.action not in event_moderation_service.EVENT_DECISION_ACTIONS:
        raise HTTPException(status_code=422, detail="invalid_action")
    try:
        result = await event_moderation_service.decide_event(
            session, event, action=payload.action, comment=payload.comment, actor=reviewer
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if bot is not None and result.owner is not None:
        await safe_send(bot, result.owner.telegram_id, result.notice)
    return _to_event_moderation_out(event)


# Post-moderation event operations — participants, attendance, points —
# the Mini App equivalent of
# app/handlers/admin/event_registration_block14.py. Distinct from the
# moderation queue above: these apply to events that are already
# approved/published, not ones still awaiting a decision.


class OperationalEventOut(BaseModel):
    id: int
    title: str
    event_date: str
    event_time: str
    location: str
    status: str
    points_for_visit: int
    registered: int
    free: int | str


@router.get("/events/operational", response_model=list[OperationalEventOut])
async def read_operational_events(
    _reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[OperationalEventOut]:
    events = await event_registration_service.list_operational_events(session)
    result: list[OperationalEventOut] = []
    for event in events:
        stats = await event_registration_service.registration_stats(session, event)
        result.append(
            OperationalEventOut(
                id=event.id,
                title=event.title,
                event_date=event.event_date.isoformat(),
                event_time=event.event_time.isoformat(),
                location=event.location,
                status=event.status,
                points_for_visit=event.points_for_visit,
                registered=stats["registered"],
                free=stats["free"],
            )
        )
    return result


class EventParticipantOut(BaseModel):
    registration_id: int
    participant_id: int
    participant_name: str
    status: str


def _to_participant_out(registration: EventRegistration, participant: User) -> EventParticipantOut:
    return EventParticipantOut(
        registration_id=registration.id,
        participant_id=participant.id,
        participant_name=f"{participant.first_name} {participant.last_name or ''}".strip(),
        status=registration.status,
    )


@router.get("/events/{event_id}/participants", response_model=list[EventParticipantOut])
async def read_event_participants(
    event_id: int,
    _reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[EventParticipantOut]:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    rows = await event_registration_service.list_participants(session, event_id)
    return [_to_participant_out(registration, participant) for registration, participant in rows]


class AttendanceIn(BaseModel):
    attended: bool


@router.post(
    "/events/{event_id}/registrations/{registration_id}/attendance",
    response_model=EventParticipantOut,
)
async def set_event_attendance_endpoint(
    event_id: int,
    registration_id: int,
    payload: AttendanceIn,
    _reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> EventParticipantOut:
    registration = await session.get(EventRegistration, registration_id)
    if registration is None or registration.event_id != event_id:
        raise HTTPException(status_code=404, detail="registration_not_found")
    participant = await session.get(User, registration.user_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    event_registration_service.set_attendance(registration, payload.attended)
    return _to_participant_out(registration, participant)


class AttendanceAwardOut(BaseModel):
    awarded_count: int


@router.post("/events/{event_id}/award-attendance-points", response_model=AttendanceAwardOut)
async def award_event_attendance_points_endpoint(
    event_id: int,
    reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> AttendanceAwardOut:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    newly_awarded = await event_registration_service.award_attendance_points(
        session, event, approved_by_id=reviewer.id
    )
    if bot is not None:
        keyboard = open_app_button(miniapp_event_url(settings.effective_miniapp_url, event.id))
        for participant in newly_awarded:
            await safe_send(
                bot,
                participant.telegram_id,
                f"Участие в мероприятии «{event.title}» подтверждено.\n"
                f"Начислено: +{event.points_for_visit} баллов.",
                keyboard,
            )
    return AttendanceAwardOut(awarded_count=len(newly_awarded))


class TaskSubmissionOut(BaseModel):
    id: int
    task_id: int
    task_title: str
    points: int
    participant_id: int
    participant_name: str
    text: str | None
    file_id: str | None
    status: str
    admin_comment: str | None


def _to_submission_out(
    submission: TaskSubmission, task: Task, participant: User
) -> TaskSubmissionOut:
    return TaskSubmissionOut(
        id=submission.id,
        task_id=task.id,
        task_title=task.title,
        points=task.points,
        participant_id=participant.id,
        participant_name=f"{participant.first_name} {participant.last_name or ''}".strip(),
        text=submission.text,
        file_id=submission.file_id,
        status=submission.status,
        admin_comment=submission.admin_comment,
    )


async def require_task_reviewer(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_tasks(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="task_reviewer_access_required")
    return user


@router.get("/task-submissions", response_model=list[TaskSubmissionOut])
async def read_task_submissions(
    _reviewer: User = Depends(require_task_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[TaskSubmissionOut]:
    submissions = await task_review_service.list_pending_submissions(session)
    result: list[TaskSubmissionOut] = []
    for submission in submissions:
        task = await session.get(Task, submission.task_id)
        participant = await session.get(User, submission.user_id)
        if task is None or participant is None:
            continue
        result.append(_to_submission_out(submission, task, participant))
    return result


class TaskSubmissionDecisionIn(BaseModel):
    action: str
    comment: str = ""


@router.post("/task-submissions/{submission_id}/decide", response_model=TaskSubmissionOut)
async def decide_task_submission_endpoint(
    submission_id: int,
    payload: TaskSubmissionDecisionIn,
    reviewer: User = Depends(require_task_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> TaskSubmissionOut:
    submission = await session.get(TaskSubmission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="submission_not_found")
    task = await session.get(Task, submission.task_id)
    participant = await session.get(User, submission.user_id)
    if task is None or participant is None:
        raise HTTPException(status_code=404, detail="submission_not_found")
    if payload.action not in task_review_service.TASK_REVIEW_ACTIONS:
        raise HTTPException(status_code=422, detail="invalid_action")
    try:
        result = await task_review_service.decide_submission(
            session,
            submission,
            task,
            participant,
            action=payload.action,
            comment=payload.comment,
            actor=reviewer,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if bot is not None and result.participant_notice:
        keyboard = open_app_button(miniapp_task_url(settings.effective_miniapp_url, task.id))
        await safe_send(bot, participant.telegram_id, result.participant_notice, keyboard)
    return _to_submission_out(submission, task, participant)


class OfferApplicationOut(BaseModel):
    id: int
    offer_id: int
    offer_title: str
    point_cost: int
    participant_id: int
    participant_name: str
    participant_balance: int
    status: str


def _to_offer_application_out(
    application: PartnerOfferApplication,
    offer: PartnerInitiative,
    participant: User,
    balance: int,
) -> OfferApplicationOut:
    return OfferApplicationOut(
        id=application.id,
        offer_id=offer.id,
        offer_title=offer.title,
        point_cost=offer.point_cost,
        participant_id=participant.id,
        participant_name=f"{participant.first_name} {participant.last_name or ''}".strip(),
        participant_balance=balance,
        status=application.status,
    )


async def require_offer_reviewer(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_partners(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="offer_reviewer_access_required")
    return user


@router.get("/offer-applications", response_model=list[OfferApplicationOut])
async def read_offer_applications(
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[OfferApplicationOut]:
    applications = await opportunity_service.list_pending_offer_applications(session)
    result: list[OfferApplicationOut] = []
    for application in applications:
        offer = await session.get(PartnerInitiative, application.initiative_id)
        participant = await session.get(User, application.user_id)
        if offer is None or participant is None:
            continue
        balance = await total_points(session, participant.id)
        result.append(_to_offer_application_out(application, offer, participant, balance))
    return result


class OfferApplicationDecisionIn(BaseModel):
    action: str


@router.post("/offer-applications/{application_id}/decide", response_model=OfferApplicationOut)
async def decide_offer_application_endpoint(
    application_id: int,
    payload: OfferApplicationDecisionIn,
    reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> OfferApplicationOut:
    application = await session.get(PartnerOfferApplication, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="application_not_found")
    offer = await session.get(PartnerInitiative, application.initiative_id)
    participant = await session.get(User, application.user_id)
    if offer is None or participant is None:
        raise HTTPException(status_code=404, detail="application_not_found")
    if payload.action not in opportunity_service.OFFER_APPLICATION_ACTIONS:
        raise HTTPException(status_code=422, detail="invalid_action")
    try:
        result = await opportunity_service.decide_offer_application(
            session, application, offer, participant, action=payload.action, actor=reviewer
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if bot is not None and result.participant_notice:
        keyboard = open_app_button(miniapp_opportunity_url(settings.effective_miniapp_url, offer.id))
        await safe_send(bot, participant.telegram_id, result.participant_notice, keyboard)
    balance = await total_points(session, participant.id)
    return _to_offer_application_out(application, offer, participant, balance)


# ---------------------------------------------------------------------------
# Partners + offer catalog management — the Mini App equivalent of
# app/handlers/admin/partners_admin.py and the create/list/toggle/archive
# half of app/handlers/admin/partner_offers_block16.py. The application
# review above only ever covered reviewing participants' applications to
# offers that already existed — there was no way to actually create or
# manage a partner or an offer itself from the Mini App.
# ---------------------------------------------------------------------------


class PartnerOut(BaseModel):
    id: int
    name: str
    description: str
    source_url: str | None
    is_active: bool
    is_archived: bool


def _to_partner_out(partner: Partner) -> PartnerOut:
    return PartnerOut(
        id=partner.id,
        name=partner.name,
        description=partner.description,
        source_url=partner.source_url,
        is_active=partner.is_active,
        is_archived=partner.is_archived,
    )


@router.get("/partners", response_model=list[PartnerOut])
async def list_partners_endpoint(
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[PartnerOut]:
    partners = await opportunity_service.list_partners(session)
    return [_to_partner_out(partner) for partner in partners]


class PartnerCreateIn(BaseModel):
    name: str
    description: str
    source_url: str = ""


@router.post("/partners", response_model=PartnerOut)
async def create_partner_endpoint(
    payload: PartnerCreateIn,
    reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> PartnerOut:
    name = payload.name.strip()
    description = payload.description.strip()
    if not name or not description:
        raise HTTPException(status_code=422, detail="name_and_description_required")
    partner = await opportunity_service.create_partner(
        session,
        name=name[:255],
        description=description,
        source_url=payload.source_url.strip()[:500] or None,
        created_by_id=reviewer.id,
    )
    return _to_partner_out(partner)


class PartnerActiveIn(BaseModel):
    active: bool


@router.post("/partners/{partner_id}/active", response_model=PartnerOut)
async def set_partner_active_endpoint(
    partner_id: int,
    payload: PartnerActiveIn,
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> PartnerOut:
    partner = await session.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="partner_not_found")
    opportunity_service.set_partner_active(partner, payload.active)
    return _to_partner_out(partner)


@router.post("/partners/{partner_id}/archive", response_model=PartnerOut)
async def archive_partner_endpoint(
    partner_id: int,
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> PartnerOut:
    partner = await session.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="partner_not_found")
    opportunity_service.archive_partner(partner)
    return _to_partner_out(partner)


class OfferAdminOut(BaseModel):
    id: int
    partner_id: int
    partner_name: str
    title: str
    description: str
    point_cost: int
    quantity: int | None
    expires_at: str | None
    instruction: str | None
    source_url: str | None
    is_active: bool
    is_archived: bool


def _to_offer_admin_out(offer: PartnerInitiative, partner: Partner) -> OfferAdminOut:
    return OfferAdminOut(
        id=offer.id,
        partner_id=partner.id,
        partner_name=partner.name,
        title=offer.title,
        description=offer.description,
        point_cost=offer.point_cost,
        quantity=offer.quantity,
        expires_at=offer.expires_at.isoformat() if offer.expires_at else None,
        instruction=offer.instruction,
        source_url=offer.source_url,
        is_active=offer.is_active,
        is_archived=offer.is_archived,
    )


@router.get("/offers", response_model=list[OfferAdminOut])
async def list_offers_endpoint(
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[OfferAdminOut]:
    rows = await opportunity_service.list_offers_admin(session)
    return [_to_offer_admin_out(offer, partner) for offer, partner in rows]


class OfferCreateIn(BaseModel):
    partner_id: int
    title: str
    description: str
    point_cost: int
    quantity: int | None = None
    expires_at: str | None = None
    instruction: str = ""
    source_url: str = ""


@router.post("/offers", response_model=OfferAdminOut)
async def create_offer_endpoint(
    payload: OfferCreateIn,
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> OfferAdminOut:
    title = payload.title.strip()
    description = payload.description.strip()
    if not title or not description:
        raise HTTPException(status_code=422, detail="title_and_description_required")
    if payload.point_cost < 0:
        raise HTTPException(status_code=422, detail="invalid_point_cost")
    if payload.quantity is not None and payload.quantity < 1:
        raise HTTPException(status_code=422, detail="invalid_quantity")
    partner = await session.get(Partner, payload.partner_id)
    if partner is None or partner.is_archived:
        raise HTTPException(status_code=404, detail="partner_not_found")
    expires_at = None
    if payload.expires_at:
        try:
            expires_at = datetime.strptime(payload.expires_at, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid_expires_at") from None
    offer = await opportunity_service.create_offer(
        session,
        partner_id=partner.id,
        title=title[:255],
        description=description[:3000],
        point_cost=payload.point_cost,
        quantity=payload.quantity,
        expires_at=expires_at,
        instruction=payload.instruction.strip()[:3000] or None,
        source_url=payload.source_url.strip()[:500] or None,
    )
    return _to_offer_admin_out(offer, partner)


class OfferActiveIn(BaseModel):
    active: bool


@router.post("/offers/{offer_id}/active", response_model=OfferAdminOut)
async def set_offer_active_endpoint(
    offer_id: int,
    payload: OfferActiveIn,
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> OfferAdminOut:
    row = await opportunity_service.get_offer_with_partner(session, offer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="offer_not_found")
    offer, partner = row
    opportunity_service.set_offer_active(offer, payload.active)
    return _to_offer_admin_out(offer, partner)


@router.post("/offers/{offer_id}/archive", response_model=OfferAdminOut)
async def archive_offer_endpoint(
    offer_id: int,
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> OfferAdminOut:
    row = await opportunity_service.get_offer_with_partner(session, offer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="offer_not_found")
    offer, partner = row
    opportunity_service.archive_offer(offer)
    return _to_offer_admin_out(offer, partner)


# ---------------------------------------------------------------------------
# People — user directory + profile actions. The Mini App equivalent of the
# bot's admin:participants list and admin:user:* card
# (app/handlers/admin/rights_block6.py, user_profile_block3_safe.py) — this
# was the single biggest admin capability that had no Mini App equivalent at
# all (search/list every user, not just pending applications; change role;
# block/unblock; archive/unarchive; grant technical permissions; award
# points or a badge directly).
# ---------------------------------------------------------------------------


async def require_people_viewer(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_view_people(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="people_view_access_required")
    return user


async def require_people_manager(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_people(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="people_manage_access_required")
    return user


async def require_permissions_manager(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_permissions(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="permissions_manage_access_required")
    return user


async def require_points_awarder(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    # Mirrors user_profile_block3_safe.py::is_admin for points/badge actions:
    # full admins always can; everyone else needs the dedicated
    # points.award grant specifically — not people.manage, which is a
    # separate, narrower grant on purpose (editing someone's role/status
    # shouldn't automatically also let you move points).
    if is_full_admin(user, settings, user.telegram_id) or "points.award" in active_permissions(user):
        return user
    raise HTTPException(status_code=403, detail="points_award_access_required")


async def require_full_admin(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    # Fulfilling a data-deletion request anonymizes a user's PII — unlike
    # the reversible block/archive actions gated on require_people_manager
    # above, that isn't something to hand to every granted people-manager;
    # deliberately restricted to full admins only.
    if not is_full_admin(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="full_admin_access_required")
    return user


async def require_maintenance_access(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    # Deliberately narrower than require_full_admin above: this wipes
    # operational data irreversibly, so — matching the bot's own
    # "🧹 Очистка тестовых данных" flow (app/handlers/admin/panel.py) exactly
    # — only the hardcoded ADMIN_IDS env var counts, not any DB role=admin
    # account. This was an explicit product decision (see task #118), not
    # an oversight: don't widen it to is_full_admin without asking first.
    if user.telegram_id not in settings.admin_ids:
        raise HTTPException(status_code=403, detail="maintenance_access_required")
    return user


# ---------------------------------------------------------------------------
# Maintenance — test-data wipe. Mini App equivalent of the bot's "🧹 Очистка
# тестовых данных" flow — see app/services/maintenance_service.py. Preview
# is read-only; the actual wipe requires the caller to echo back
# CONFIRMATION_PHRASE verbatim, validated server-side (never trust a
# client-only confirm step for something this destructive).
# ---------------------------------------------------------------------------


class MaintenancePreviewOut(BaseModel):
    counts: dict[str, int]
    total: int
    confirmation_phrase: str


@router.get("/maintenance/preview", response_model=MaintenancePreviewOut)
async def read_maintenance_preview(
    admin: User = Depends(require_maintenance_access),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> MaintenancePreviewOut:
    counts = await reset_preview(session, settings.admin_ids)
    visible = {name: value for name, value in counts.items() if name in COUNT_LABELS}
    return MaintenancePreviewOut(counts=visible, total=sum(counts.values()), confirmation_phrase=CONFIRMATION_PHRASE)


class MaintenanceResetIn(BaseModel):
    confirmation_phrase: str


class MaintenanceResetOut(BaseModel):
    counts: dict[str, int]
    total: int


@router.post("/maintenance/reset", response_model=MaintenanceResetOut)
async def run_maintenance_reset(
    payload: MaintenanceResetIn,
    admin: User = Depends(require_maintenance_access),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> MaintenanceResetOut:
    if payload.confirmation_phrase.strip() != CONFIRMATION_PHRASE:
        raise HTTPException(status_code=422, detail="confirmation_phrase_mismatch")
    counts = await reset_operational_data(session, settings.admin_ids)
    visible = {name: value for name, value in counts.items() if name in COUNT_LABELS}
    return MaintenanceResetOut(counts=visible, total=sum(counts.values()))


class UserListItemOut(BaseModel):
    id: int
    telegram_id: int
    first_name: str
    last_name: str | None
    username: str | None
    role: str
    application_status: str
    is_blocked: bool
    is_archived: bool


class UserListOut(BaseModel):
    items: list[UserListItemOut]
    total: int


@router.get("/users", response_model=UserListOut)
async def list_users_endpoint(
    query: str = "",
    role: str | None = None,
    include_archived: bool = False,
    limit: int = 30,
    offset: int = 0,
    _viewer: User = Depends(require_people_viewer),
    session: AsyncSession = Depends(get_session),
) -> UserListOut:
    rows, total = await user_management_service.search_users(
        session,
        query=query,
        role=role,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return UserListOut(
        items=[
            UserListItemOut(
                id=u.id,
                telegram_id=u.telegram_id,
                first_name=u.first_name,
                last_name=u.last_name,
                username=u.username,
                role=u.role,
                application_status=u.application_status,
                is_blocked=u.is_blocked,
                is_archived=u.is_archived,
            )
            for u in rows
        ],
        total=total,
    )


class BadgeOut(BaseModel):
    id: int
    name: str


class SocialLinkOut(BaseModel):
    platform: str
    url: str


class UserDetailOut(BaseModel):
    id: int
    telegram_id: int
    first_name: str
    last_name: str | None
    username: str | None
    role: str
    application_status: str
    participation_status: str
    is_blocked: bool
    is_archived: bool
    city: str | None
    phone: str | None
    email: str | None
    occupation: str | None
    motivation: str | None
    points_balance: int
    portfolio_count: int
    badges: list[BadgeOut]
    available_badges: list[BadgeOut]
    permissions: dict[str, bool]
    social_links: list[SocialLinkOut]
    can_manage: bool
    can_manage_permissions: bool
    can_award_points: bool


async def _build_user_detail_out(
    session: AsyncSession, target: User, viewer: User, settings: Settings
) -> UserDetailOut:
    balance = await total_points(session, target.id)
    owned = await user_management_service.user_badges(session, target.id)
    available = await user_management_service.available_badges(session, target.id)
    links = await user_management_service.social_links(session, target.id)
    active = user_management_service.active_permission_set(target)
    return UserDetailOut(
        id=target.id,
        telegram_id=target.telegram_id,
        first_name=target.first_name,
        last_name=target.last_name,
        username=target.username,
        role=target.role,
        application_status=target.application_status,
        participation_status=target.participation_status,
        is_blocked=target.is_blocked,
        is_archived=target.is_archived,
        city=target.city,
        phone=target.phone,
        email=target.email,
        occupation=target.occupation,
        motivation=target.motivation,
        points_balance=balance,
        portfolio_count=await user_management_service.portfolio_count(session, target.id),
        badges=[BadgeOut(id=b.id, name=b.name) for b in owned],
        available_badges=[BadgeOut(id=b.id, name=b.name) for b in available],
        permissions={permission: permission in active for permission in PERMISSIONS},
        social_links=[SocialLinkOut(platform=link.platform, url=link.url) for link in links],
        can_manage=can_manage_people(viewer, settings, viewer.telegram_id),
        can_manage_permissions=can_manage_permissions(viewer, settings, viewer.telegram_id),
        can_award_points=is_full_admin(viewer, settings, viewer.telegram_id)
        or "points.award" in active_permissions(viewer),
    )


@router.get("/users/{user_id}", response_model=UserDetailOut)
async def read_user_detail(
    user_id: int,
    viewer: User = Depends(require_people_viewer),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> UserDetailOut:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    return await _build_user_detail_out(session, target, viewer, settings)


class RoleChangeIn(BaseModel):
    role: str


@router.post("/users/{user_id}/role", response_model=UserDetailOut)
async def change_user_role(
    user_id: int,
    payload: RoleChangeIn,
    manager: User = Depends(require_people_manager),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> UserDetailOut:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    try:
        new_role = RoleEnum(payload.role)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_role") from None
    decision = await user_management_service.change_role(
        session,
        actor=manager,
        actor_telegram_id=manager.telegram_id,
        target=target,
        new_role=new_role,
        settings=settings,
    )
    if not decision.allowed:
        raise HTTPException(status_code=409, detail=decision.reason or "cannot_change_role")
    if bot is not None:
        await sync_user_chat_access(bot, settings, session, target)
        await safe_send(
            bot,
            target.telegram_id,
            f"Ваша роль в ЭРА обновлена: {ROLE_LABELS.get(new_role, new_role.value)}\n\n"
            "Новые возможности уже доступны в меню",
            main_inline_keyboard(
                privileged=new_role in PRIVILEGED_ROLES,
                admin=new_role == RoleEnum.ADMIN,
                miniapp_url=settings.effective_miniapp_url,
            ),
        )
    return await _build_user_detail_out(session, target, manager, settings)


class BlockIn(BaseModel):
    blocked: bool


@router.post("/users/{user_id}/block", response_model=UserDetailOut)
async def set_user_blocked(
    user_id: int,
    payload: BlockIn,
    manager: User = Depends(require_people_manager),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> UserDetailOut:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    decision = await user_management_service.set_blocked(
        session, actor=manager, target=target, settings=settings, blocked=payload.blocked
    )
    if not decision.allowed:
        raise HTTPException(status_code=409, detail=decision.reason or "cannot_change_access")
    if bot is not None:
        await sync_user_chat_access(bot, settings, session, target)
    return await _build_user_detail_out(session, target, manager, settings)


class ArchiveIn(BaseModel):
    archived: bool


@router.post("/users/{user_id}/archive", response_model=UserDetailOut)
async def set_user_archived(
    user_id: int,
    payload: ArchiveIn,
    manager: User = Depends(require_people_manager),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> UserDetailOut:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    decision = await user_management_service.set_archived(
        session, actor=manager, target=target, settings=settings, archived=payload.archived
    )
    if not decision.allowed:
        raise HTTPException(status_code=409, detail=decision.reason or "cannot_change_access")
    if bot is not None:
        await sync_user_chat_access(bot, settings, session, target)
    return await _build_user_detail_out(session, target, manager, settings)


class PermissionToggleOut(BaseModel):
    permission: str
    enabled: bool


@router.post("/users/{user_id}/permissions/{permission}", response_model=PermissionToggleOut)
async def toggle_user_permission(
    user_id: int,
    permission: str,
    manager: User = Depends(require_permissions_manager),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> PermissionToggleOut:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    decision, enabled = await user_management_service.toggle_permission(
        session, actor=manager, target=target, permission=permission
    )
    if not decision.allowed:
        raise HTTPException(status_code=409, detail=decision.reason or "cannot_change_permission")
    return PermissionToggleOut(permission=permission, enabled=enabled)


# ---------------------------------------------------------------------------
# Data rights — review queue for self-service account-deletion requests.
# See app/services/data_rights_service.py: fulfilling anonymizes the
# target's PII and archives the row, it does not hard-delete it.
# ---------------------------------------------------------------------------


class DeletionRequestOut(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str | None
    telegram_id: int
    note: str | None
    status: str
    created_at: str


async def _to_deletion_request_out(
    session: AsyncSession, request: DataDeletionRequest
) -> DeletionRequestOut:
    target = await session.get(User, request.user_id)
    return DeletionRequestOut(
        id=request.id,
        user_id=request.user_id,
        first_name=target.first_name if target else "—",
        last_name=target.last_name if target else None,
        telegram_id=target.telegram_id if target else 0,
        note=request.note,
        status=request.status,
        created_at=request.created_at.isoformat(),
    )


@router.get("/data-deletion-requests", response_model=list[DeletionRequestOut])
async def list_deletion_requests_endpoint(
    _admin: User = Depends(require_full_admin),
    session: AsyncSession = Depends(get_session),
) -> list[DeletionRequestOut]:
    requests = await data_rights_service.list_deletion_requests(session)
    return [await _to_deletion_request_out(session, request) for request in requests]


class DeletionDecisionIn(BaseModel):
    approve: bool


@router.post("/data-deletion-requests/{request_id}/fulfill", response_model=DeletionRequestOut)
async def fulfill_deletion_request_endpoint(
    request_id: int,
    payload: DeletionDecisionIn,
    admin: User = Depends(require_full_admin),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> DeletionRequestOut:
    request = await session.get(DataDeletionRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="request_not_found")
    await data_rights_service.fulfill_deletion_request(
        session, request, admin=admin, approve=payload.approve
    )
    return await _to_deletion_request_out(session, request)


class PointsAwardIn(BaseModel):
    amount: int
    reason: str


class PointsAwardOut(BaseModel):
    balance: int


@router.post("/users/{user_id}/points", response_model=PointsAwardOut)
async def award_user_points(
    user_id: int,
    payload: PointsAwardIn,
    awarder: User = Depends(require_points_awarder),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> PointsAwardOut:
    reason = payload.reason.strip()
    if payload.amount == 0 or abs(payload.amount) > user_management_service.MAX_POINTS_ADJUSTMENT:
        raise HTTPException(status_code=422, detail="invalid_amount")
    if not reason:
        raise HTTPException(status_code=422, detail="comment_required")
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    balance = await user_management_service.award_points(
        session, target=target, amount=payload.amount, reason=reason, approved_by_id=awarder.id
    )
    if bot is not None:
        await safe_send(
            bot,
            target.telegram_id,
            f"Ваш баланс изменён на {payload.amount:+d} баллов\nПричина: {reason}\n\n"
            f"Текущий баланс: {balance} баллов",
        )
    return PointsAwardOut(balance=balance)


class BadgeAwardIn(BaseModel):
    reason: str


@router.post("/users/{user_id}/badges/{badge_id}", response_model=BadgeOut)
async def award_user_badge(
    user_id: int,
    badge_id: int,
    payload: BadgeAwardIn,
    awarder: User = Depends(require_points_awarder),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> BadgeOut:
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="comment_required")
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    badge = await session.get(Badge, badge_id)
    if badge is None:
        raise HTTPException(status_code=404, detail="badge_not_found")
    awarded = await user_management_service.award_badge(
        session, target=target, badge=badge, reason=reason, awarded_by_id=awarder.id
    )
    if not awarded:
        raise HTTPException(status_code=409, detail="already_awarded")
    if bot is not None:
        await safe_send(bot, target.telegram_id, f"Вы получили знак «{badge.name}» 🌟\n\n{reason}")
    return BadgeOut(id=badge.id, name=badge.name)


# ---------------------------------------------------------------------------
# Offices — "Должности и ответственность". The Mini App equivalent of
# app/handlers/admin/offices_management.py (list/view/delete) and the
# office_assign/office_remove/office_new handlers in panel.py — one
# cohesive feature split across two Bot files, kept together here.
# ---------------------------------------------------------------------------


class OfficeAssignmentOut(BaseModel):
    assignment_id: int
    user_id: int
    user_name: str


class OfficeOut(BaseModel):
    id: int
    title: str
    description: str | None
    is_active: bool
    assignments: list[OfficeAssignmentOut]


async def _to_office_out(session: AsyncSession, office) -> OfficeOut:
    rows = await office_management_service.list_assignments(session, office.id)
    return OfficeOut(
        id=office.id,
        title=office.title,
        description=office.description,
        is_active=office.is_active,
        assignments=[
            OfficeAssignmentOut(
                assignment_id=assignment.id,
                user_id=user.id,
                user_name=f"{user.first_name} {user.last_name or ''}".strip(),
            )
            for assignment, user in rows
        ],
    )


@router.get("/offices", response_model=list[OfficeOut])
async def list_offices_endpoint(
    _manager: User = Depends(require_people_manager),
    session: AsyncSession = Depends(get_session),
) -> list[OfficeOut]:
    offices = await office_management_service.list_offices(session)
    return [await _to_office_out(session, office) for office in offices]


class OfficeCreateIn(BaseModel):
    title: str
    description: str = ""


@router.post("/offices", response_model=OfficeOut)
async def create_office_endpoint(
    payload: OfficeCreateIn,
    _manager: User = Depends(require_people_manager),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> OfficeOut:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="title_required")
    office = await office_management_service.create_office(
        session, title=title[:150], description=payload.description.strip()[:1000] or None
    )
    return await _to_office_out(session, office)


@router.post("/offices/{office_id}/delete", response_model=OfficeOut)
async def delete_office_endpoint(
    office_id: int,
    manager: User = Depends(require_people_manager),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> OfficeOut:
    office = await session.get(Office, office_id)
    if office is None:
        raise HTTPException(status_code=404, detail="office_not_found")
    await office_management_service.delete_office(session, office, actor_id=manager.id)
    return await _to_office_out(session, office)


@router.get("/offices/assignable-users", response_model=list[UserListItemOut])
async def search_assignable_users_endpoint(
    query: str = "",
    _manager: User = Depends(require_people_manager),
    session: AsyncSession = Depends(get_session),
) -> list[UserListItemOut]:
    if not query.strip():
        return []
    users = await office_management_service.search_assignable_users(session, query)
    return [
        UserListItemOut(
            id=u.id,
            telegram_id=u.telegram_id,
            first_name=u.first_name,
            last_name=u.last_name,
            username=u.username,
            role=u.role,
            application_status=u.application_status,
            is_blocked=u.is_blocked,
            is_archived=u.is_archived,
        )
        for u in users
    ]


class OfficeAssignIn(BaseModel):
    user_id: int


@router.post("/offices/{office_id}/assign", response_model=OfficeOut)
async def assign_office_endpoint(
    office_id: int,
    payload: OfficeAssignIn,
    manager: User = Depends(require_people_manager),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> OfficeOut:
    office = await session.get(Office, office_id)
    if office is None:
        raise HTTPException(status_code=404, detail="office_not_found")
    target = await session.get(User, payload.user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    await office_management_service.assign_office(
        session, office_id=office_id, user_id=payload.user_id, appointed_by_id=manager.id
    )
    return await _to_office_out(session, office)


@router.post("/offices/assignments/{assignment_id}/remove", response_model=OfficeOut)
async def remove_office_assignment_endpoint(
    assignment_id: int,
    _manager: User = Depends(require_people_manager),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> OfficeOut:
    assignment = await session.get(UserOffice, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="assignment_not_found")
    office = await session.get(Office, assignment.office_id)
    if office is None:
        raise HTTPException(status_code=404, detail="office_not_found")
    office_management_service.remove_assignment(assignment)
    return await _to_office_out(session, office)


# ---------------------------------------------------------------------------
# Auctions — the Mini App equivalent of the admin half of
# app/handlers/admin/auction_block17.py (create lot, confirm winner, mark
# delivered, cancel). The participant side (browse + bid) is
# /api/v1/auctions, mounted separately since it's a participant-facing
# feature, not an admin one.
# ---------------------------------------------------------------------------


class AuctionBidOut(BaseModel):
    bid_id: int
    bidder_id: int
    bidder_name: str
    amount: int


class AuctionAdminOut(BaseModel):
    id: int
    title: str
    description: str
    status: str
    minimum_bid: int
    bid_step: int
    ends_at: str
    top_bid: int | None
    bids: list[AuctionBidOut]


async def _to_auction_admin_out(session: AsyncSession, auction) -> AuctionAdminOut:
    rows = await auction_service.list_bids(session, auction.id)
    top_bid, _ = await auction_service.top_bid_with_user(session, auction.id)
    return AuctionAdminOut(
        id=auction.id,
        title=auction.title,
        description=auction.description,
        status=auction.status,
        minimum_bid=auction.minimum_bid,
        bid_step=auction.bid_step,
        ends_at=auction.ends_at.isoformat(),
        top_bid=top_bid.amount if top_bid else None,
        bids=[
            AuctionBidOut(
                bid_id=bid.id,
                bidder_id=bidder.id,
                bidder_name=auction_service.bidder_name(bidder),
                amount=bid.amount,
            )
            for bid, bidder in rows
        ],
    )


@router.get("/auctions", response_model=list[AuctionAdminOut])
async def list_auctions_endpoint(
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[AuctionAdminOut]:
    auctions = await auction_service.list_all_auctions(session)
    return [await _to_auction_admin_out(session, auction) for auction in auctions]


class AuctionCreateIn(BaseModel):
    title: str
    description: str
    minimum_bid: int
    bid_step: int
    ends_at: str  # "YYYY-MM-DD HH:MM" in the server's configured timezone


@router.post("/auctions", response_model=AuctionAdminOut)
async def create_auction_endpoint(
    payload: AuctionCreateIn,
    reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> AuctionAdminOut:
    title = payload.title.strip()
    description = payload.description.strip()
    if not title or not description:
        raise HTTPException(status_code=422, detail="title_and_description_required")
    if payload.minimum_bid <= 0 or payload.bid_step <= 0:
        raise HTTPException(status_code=422, detail="invalid_bid_amount")
    try:
        local_value = datetime.strptime(payload.ends_at, "%Y-%m-%d %H:%M").replace(
            tzinfo=ZoneInfo(settings.timezone)
        )
    except (ValueError, KeyError):
        raise HTTPException(status_code=422, detail="invalid_ends_at") from None
    ends_at = local_value.astimezone(timezone.utc)
    if ends_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="ends_at_must_be_future")
    auction = await auction_service.create_auction(
        session,
        title=title[:255],
        description=description[:3000],
        minimum_bid=payload.minimum_bid,
        bid_step=payload.bid_step,
        ends_at=ends_at,
        created_by_id=reviewer.id,
    )
    return await _to_auction_admin_out(session, auction)


@router.post("/auctions/{auction_id}/confirm-winner", response_model=AuctionAdminOut)
async def confirm_auction_winner_endpoint(
    auction_id: int,
    reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> AuctionAdminOut:
    auction = await session.get(Auction, auction_id)
    if auction is None:
        raise HTTPException(status_code=404, detail="auction_not_found")
    if auction.status != "active":
        raise HTTPException(status_code=409, detail="auction_already_closed")
    if datetime.now(timezone.utc) < auction.ends_at:
        raise HTTPException(status_code=409, detail="bidding_still_open")
    result = await auction_service.confirm_winner(session, auction, actor_id=reviewer.id)
    if result is None:
        raise HTTPException(status_code=409, detail="no_valid_bidder")
    bid, winner = result
    if bot is not None:
        await safe_send(
            bot,
            winner.telegram_id,
            f"Вы выиграли аукцион «{auction.title}».\nСписано: {bid.amount} баллов.\n"
            "Команда ЭРА свяжется с Вами для передачи лота.",
        )
    return await _to_auction_admin_out(session, auction)


@router.post("/auctions/{auction_id}/deliver", response_model=AuctionAdminOut)
async def deliver_auction_endpoint(
    auction_id: int,
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> AuctionAdminOut:
    auction = await session.get(Auction, auction_id)
    if auction is None:
        raise HTTPException(status_code=404, detail="auction_not_found")
    if auction.status != "completed":
        raise HTTPException(status_code=409, detail="cannot_mark_delivered")
    winner = await auction_service.mark_delivered(session, auction)
    if bot is not None and winner is not None:
        await safe_send(
            bot, winner.telegram_id, f"Лот «{auction.title}» отмечен как переданный. Спасибо за участие в аукционе ЭРА."
        )
    return await _to_auction_admin_out(session, auction)


@router.post("/auctions/{auction_id}/cancel", response_model=AuctionAdminOut)
async def cancel_auction_endpoint(
    auction_id: int,
    reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> AuctionAdminOut:
    auction = await session.get(Auction, auction_id)
    if auction is None:
        raise HTTPException(status_code=404, detail="auction_not_found")
    if auction.status != "active":
        raise HTTPException(status_code=409, detail="auction_already_closed")
    if datetime.now(timezone.utc) < auction.ends_at:
        raise HTTPException(status_code=409, detail="bidding_still_open")
    await auction_service.cancel_auction(session, auction, actor_id=reviewer.id)
    return await _to_auction_admin_out(session, auction)


# ---------------------------------------------------------------------------
# Surveys — the Mini App equivalent of app/handlers/admin/surveys_analytics.py
# (list/create/edit/send/archive, view responses). Excel export of results is
# not ported yet — it remains a Bot-only capability for now (tracked in
# docs/ERA_PLATFORM_PROGRESS.md).
# ---------------------------------------------------------------------------


class SurveyAdminOut(BaseModel):
    id: int
    title: str
    description: str | None
    questions: list[str]
    status: str
    is_monthly: bool
    sent_at: str | None
    response_count: int


async def _to_survey_admin_out(session: AsyncSession, survey: AdminSurvey) -> SurveyAdminOut:
    return SurveyAdminOut(
        id=survey.id,
        title=survey.title,
        description=survey.description,
        questions=survey_service.survey_questions(survey),
        status=survey.status,
        is_monthly=survey.is_monthly,
        sent_at=survey.sent_at.isoformat() if survey.sent_at else None,
        response_count=await survey_admin_service.response_count(session, survey.id),
    )


@router.get("/surveys", response_model=list[SurveyAdminOut])
async def list_surveys_endpoint(
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> list[SurveyAdminOut]:
    surveys = await survey_admin_service.list_surveys(session)
    return [await _to_survey_admin_out(session, survey) for survey in surveys]


@router.post("/surveys/monthly", response_model=SurveyAdminOut)
async def get_or_create_monthly_survey_endpoint(
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> SurveyAdminOut:
    survey = await survey_admin_service.get_or_create_monthly_survey(session, created_by_id=admin.id)
    return await _to_survey_admin_out(session, survey)


class SurveyCreateIn(BaseModel):
    title: str
    description: str | None = None
    questions: list[str]


def _clean_questions(questions: list[str]) -> list[str]:
    cleaned = [q.strip() for q in questions if q.strip()]
    if not cleaned:
        raise HTTPException(status_code=422, detail="questions_required")
    return cleaned


@router.post("/surveys", response_model=SurveyAdminOut)
async def create_survey_endpoint(
    payload: SurveyCreateIn,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> SurveyAdminOut:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="title_required")
    questions = _clean_questions(payload.questions)
    survey = await survey_admin_service.create_survey(
        session,
        title=title[:255],
        description=(payload.description or "").strip() or None,
        questions=questions,
        created_by_id=admin.id,
    )
    return await _to_survey_admin_out(session, survey)


async def _get_survey_or_404(session: AsyncSession, survey_id: int) -> AdminSurvey:
    survey = await session.get(AdminSurvey, survey_id)
    if survey is None:
        raise HTTPException(status_code=404, detail="survey_not_found")
    return survey


@router.post("/surveys/{survey_id}/edit", response_model=SurveyAdminOut)
async def update_survey_endpoint(
    survey_id: int,
    payload: SurveyCreateIn,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> SurveyAdminOut:
    survey = await _get_survey_or_404(session, survey_id)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="title_required")
    questions = _clean_questions(payload.questions)
    survey_admin_service.update_survey(
        survey,
        title=title[:255],
        description=(payload.description or "").strip() or None,
        questions=questions,
        updated_by_id=admin.id,
    )
    return await _to_survey_admin_out(session, survey)


@router.post("/surveys/{survey_id}/archive", response_model=SurveyAdminOut)
async def archive_survey_endpoint(
    survey_id: int,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> SurveyAdminOut:
    survey = await _get_survey_or_404(session, survey_id)
    survey_admin_service.archive_survey(survey, updated_by_id=admin.id)
    return await _to_survey_admin_out(session, survey)


@router.post("/surveys/{survey_id}/send", response_model=SurveyAdminOut)
async def send_survey_endpoint(
    survey_id: int,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> SurveyAdminOut:
    survey = await _get_survey_or_404(session, survey_id)
    if survey.status == "archived":
        raise HTTPException(status_code=409, detail="survey_archived")
    questions = survey_service.survey_questions(survey)
    if not questions:
        raise HTTPException(status_code=422, detail="questions_required")
    recipients = await survey_admin_service.send_recipients(session)
    if bot is not None and recipients:
        # Mirrors app/handlers/admin/surveys_analytics.py::send_survey's own
        # text exactly, so a Mini App-triggered send reads identically to a
        # Bot-triggered one.
        await safe_send_survey_invites(bot, survey, recipients)
    survey_admin_service.mark_sent(survey, timezone_name=settings.timezone, updated_by_id=admin.id)
    return await _to_survey_admin_out(session, survey)


async def safe_send_survey_invites(bot: Bot, survey: AdminSurvey, recipients: list[User]) -> None:
    await broadcast_detailed(
        bot,
        [participant.telegram_id for participant in recipients],
        f"🗳 {survey.title}\n\n"
        f"{survey.description or 'Команда ЭРА собирает обратную связь, чтобы принимать решения точнее'}\n\n"
        "Ответить можно в приложении ЭРА, вкладка «Опросы»",
    )


class SurveyResponseOut(BaseModel):
    user_id: int
    user_name: str
    submitted_at: str | None
    answers: list[dict[str, str]]


@router.get("/surveys/{survey_id}/responses", response_model=list[SurveyResponseOut])
async def list_survey_responses_endpoint(
    survey_id: int,
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> list[SurveyResponseOut]:
    await _get_survey_or_404(session, survey_id)
    rows = await survey_admin_service.list_responses(session, survey_id)
    return [
        SurveyResponseOut(
            user_id=respondent.id,
            user_name=f"{respondent.first_name} {respondent.last_name or ''}".strip(),
            submitted_at=response.submitted_at.isoformat() if response.submitted_at else None,
            answers=survey_service.answer_items(response),
        )
        for response, respondent in rows
    ]


# ---------------------------------------------------------------------------
# Rewards & Redemptions — the Mini App equivalent of the admin:reward*/
# admin:redemption* handlers in app/handlers/admin/panel.py (points-shop
# catalog: create/disable a reward, answer a redemption request, then
# confirm the exchange or reject it). A reward's cost is fixed up front,
# distinct from Auctions where the cost is decided by bidding.
# ---------------------------------------------------------------------------


class RewardAdminOut(BaseModel):
    id: int
    name: str
    description: str
    point_cost: int
    quantity: int | None
    is_active: bool


def _to_reward_admin_out(reward) -> RewardAdminOut:
    return RewardAdminOut(
        id=reward.id,
        name=reward.name,
        description=reward.description,
        point_cost=reward.point_cost,
        quantity=reward.quantity,
        is_active=reward.is_active,
    )


@router.get("/rewards", response_model=list[RewardAdminOut])
async def list_rewards_admin_endpoint(
    _awarder: User = Depends(require_points_awarder),
    session: AsyncSession = Depends(get_session),
) -> list[RewardAdminOut]:
    rewards = await redemption_service.list_rewards_admin(session, include_inactive=True)
    return [_to_reward_admin_out(reward) for reward in rewards]


class RewardCreateIn(BaseModel):
    name: str
    description: str
    point_cost: int
    quantity: int | None = None


@router.post("/rewards", response_model=RewardAdminOut)
async def create_reward_endpoint(
    payload: RewardCreateIn,
    awarder: User = Depends(require_points_awarder),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> RewardAdminOut:
    name = payload.name.strip()
    description = payload.description.strip()
    if not name or not description:
        raise HTTPException(status_code=422, detail="name_and_description_required")
    if payload.point_cost <= 0:
        raise HTTPException(status_code=422, detail="invalid_point_cost")
    if payload.quantity is not None and payload.quantity < 0:
        raise HTTPException(status_code=422, detail="invalid_quantity")
    reward = await redemption_service.create_reward(
        session,
        name=name[:255],
        description=description[:2000],
        point_cost=payload.point_cost,
        quantity=payload.quantity,
        created_by_id=awarder.id,
    )
    return _to_reward_admin_out(reward)


@router.post("/rewards/{reward_id}/disable", response_model=RewardAdminOut)
async def disable_reward_endpoint(
    reward_id: int,
    _awarder: User = Depends(require_points_awarder),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> RewardAdminOut:
    reward = await session.get(RewardItem, reward_id)
    if reward is None:
        raise HTTPException(status_code=404, detail="reward_not_found")
    redemption_service.disable_reward(reward)
    return _to_reward_admin_out(reward)


class RedemptionAdminOut(BaseModel):
    id: int
    reward_id: int
    reward_name: str
    user_id: int
    user_name: str
    points_spent: int
    status: str
    admin_comment: str | None


@router.get("/redemptions", response_model=list[RedemptionAdminOut])
async def list_redemptions_endpoint(
    _awarder: User = Depends(require_points_awarder),
    session: AsyncSession = Depends(get_session),
) -> list[RedemptionAdminOut]:
    rows = await redemption_service.list_open_redemptions(session)
    return [
        RedemptionAdminOut(
            id=redemption.id,
            reward_id=reward.id,
            reward_name=reward.name,
            user_id=respondent.id,
            user_name=f"{respondent.first_name} {respondent.last_name or ''}".strip(),
            points_spent=redemption.points_spent,
            status=redemption.status,
            admin_comment=redemption.admin_comment,
        )
        for redemption, reward, respondent in rows
    ]


async def _get_redemption_or_404(session: AsyncSession, redemption_id: int) -> RewardRedemption:
    redemption = await session.get(RewardRedemption, redemption_id)
    if redemption is None:
        raise HTTPException(status_code=404, detail="redemption_not_found")
    return redemption


class RedemptionAnswerIn(BaseModel):
    answer: str


@router.post("/redemptions/{redemption_id}/answer", response_model=RedemptionAdminOut)
async def answer_redemption_endpoint(
    redemption_id: int,
    payload: RedemptionAnswerIn,
    awarder: User = Depends(require_points_awarder),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> RedemptionAdminOut:
    redemption = await _get_redemption_or_404(session, redemption_id)
    if redemption.status not in redemption_service.OPEN_REDEMPTION_STATUSES:
        raise HTTPException(status_code=409, detail="redemption_already_closed")
    answer = payload.answer.strip()
    if not answer:
        raise HTTPException(status_code=422, detail="answer_required")
    reward = await session.get(RewardItem, redemption.reward_id)
    target = await session.get(User, redemption.user_id)
    if reward is None or target is None:
        raise HTTPException(status_code=404, detail="reward_or_user_not_found")
    if bot is not None:
        # Fire-and-forget, like every other admin notification in this
        # router — the Bot's own chat flow refused to record an answer it
        # couldn't deliver because the very next message *was* the
        # delivery confirmation; the Mini App's Redemptions list isn't
        # chat-mediated, so a transient Telegram delivery failure
        # shouldn't block the admin from recording their reply here.
        await safe_send(
            bot,
            target.telegram_id,
            f"🎁 Ответ по возможности «{reward.name}»\n\n{answer}\n\n"
            "Баллы пока не списаны — окончательное решение об обмене ещё не принято",
        )
    await redemption_service.answer_redemption(session, redemption, answer=answer, admin_id=awarder.id)
    return RedemptionAdminOut(
        id=redemption.id,
        reward_id=reward.id,
        reward_name=reward.name,
        user_id=target.id,
        user_name=f"{target.first_name} {target.last_name or ''}".strip(),
        points_spent=redemption.points_spent,
        status=redemption.status,
        admin_comment=redemption.admin_comment,
    )


@router.post("/redemptions/{redemption_id}/exchange", response_model=RedemptionAdminOut)
async def exchange_redemption_endpoint(
    redemption_id: int,
    awarder: User = Depends(require_points_awarder),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> RedemptionAdminOut:
    result = await redemption_service.exchange_redemption(session, redemption_id=redemption_id, admin_id=awarder.id)
    if result.code != "exchanged":
        raise HTTPException(status_code=409, detail=result.code)
    target = await session.get(User, result.redemption.user_id)
    if bot is not None and target is not None:
        balance = await total_points(session, result.redemption.user_id)
        await safe_send(
            bot,
            target.telegram_id,
            f"✅ Возможность «{result.reward.name}» подтверждена\n\n"
            f"Списано: {result.redemption.points_spent} баллов\n"
            f"Остаток: {balance} баллов\n\n"
            "Команда ЭРА свяжется с Вами по дальнейшим шагам",
        )
    return RedemptionAdminOut(
        id=result.redemption.id,
        reward_id=result.reward.id,
        reward_name=result.reward.name,
        user_id=result.redemption.user_id,
        user_name=f"{target.first_name} {target.last_name or ''}".strip() if target else "",
        points_spent=result.redemption.points_spent,
        status=result.redemption.status,
        admin_comment=result.redemption.admin_comment,
    )


@router.post("/redemptions/{redemption_id}/reject", response_model=RedemptionAdminOut)
async def reject_redemption_endpoint(
    redemption_id: int,
    awarder: User = Depends(require_points_awarder),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> RedemptionAdminOut:
    result = await redemption_service.reject_redemption(session, redemption_id=redemption_id, admin_id=awarder.id)
    if result.code != "rejected":
        raise HTTPException(status_code=409, detail=result.code)
    target = await session.get(User, result.redemption.user_id)
    if bot is not None and target is not None and result.reward is not None:
        await safe_send(
            bot,
            target.telegram_id,
            f"Заявка на «{result.reward.name}» отклонена. Баллы с Вашего баланса не списывались",
        )
    return RedemptionAdminOut(
        id=result.redemption.id,
        reward_id=result.reward.id if result.reward else 0,
        reward_name=result.reward.name if result.reward else "",
        user_id=result.redemption.user_id,
        user_name=f"{target.first_name} {target.last_name or ''}".strip() if target else "",
        points_spent=result.redemption.points_spent,
        status=result.redemption.status,
        admin_comment=result.redemption.admin_comment,
    )


# ---------------------------------------------------------------------------
# Event Activities — the Mini App equivalent of the *live* (not
# app/handlers/admin/panel.py's own dead, shadowed) admin handlers:
# app/handlers/admin/event_activities_stability.py (list/review/decide),
# event_activities_block15.py (create), event_activities_block7.py
# (send-to-participants). Create/send/review is per-event; final review
# also covers submissions a leader already pre-approved (see
# app/api/v1/leader.py's own activities endpoints).
# ---------------------------------------------------------------------------


class EventActivityAdminOut(BaseModel):
    id: int
    title: str
    description: str
    submission_type: str
    points: int
    is_active: bool


@router.get("/events/{event_id}/activities", response_model=list[EventActivityAdminOut])
async def list_event_activities_endpoint(
    event_id: int,
    _reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[EventActivityAdminOut]:
    activities = await event_activity_service.list_activities_admin(session, event_id)
    return [
        EventActivityAdminOut(
            id=a.id, title=a.title, description=a.description, submission_type=a.submission_type,
            points=a.points, is_active=a.is_active,
        )
        for a in activities
    ]


class EventActivityCreateIn(BaseModel):
    lines: str


class EventActivityCreateOut(BaseModel):
    created: int
    rejected: int
    activities: list[EventActivityAdminOut]


@router.post("/events/{event_id}/activities", response_model=EventActivityCreateOut)
async def create_event_activities_endpoint(
    event_id: int,
    payload: EventActivityCreateIn,
    _reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> EventActivityCreateOut:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    created, rejected = await event_activity_service.create_activities_bulk(session, event, payload.lines)
    if not created:
        raise HTTPException(status_code=422, detail="no_valid_activities")
    activities = await event_activity_service.list_activities_admin(session, event_id)
    return EventActivityCreateOut(
        created=created,
        rejected=rejected,
        activities=[
            EventActivityAdminOut(
                id=a.id, title=a.title, description=a.description, submission_type=a.submission_type,
                points=a.points, is_active=a.is_active,
            )
            for a in activities
        ],
    )


@router.post("/events/{event_id}/activities/send")
async def send_event_activities_endpoint(
    event_id: int,
    reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> dict[str, int]:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    if event_activity_service.activities_already_sent(event):
        raise HTTPException(status_code=409, detail="already_sent")
    activities = await event_activity_service.list_activities_admin(session, event_id)
    active_activities = [a for a in activities if a.is_active]
    if not active_activities:
        raise HTTPException(status_code=422, detail="no_active_activities")
    recipients = await event_activity_service.send_recipients(session, event_id)
    sent = 0
    if bot is not None:
        for target in recipients:
            for activity in active_activities:
                await safe_send(
                    bot,
                    target.telegram_id,
                    f"✨ Активность после мероприятия\n\n{event.title}\n\n{activity.title}\n{activity.description}\n\n"
                    f"Формат: {activity.submission_type}\nБаллы: {activity.points}\n\n"
                    "Открыть и отправить результат — в приложении ЭРА.",
                    reply_markup=open_app_button(settings.effective_miniapp_url),
                )
            sent += 1
    event_activity_service.mark_activities_sent(event)
    return {"sent": sent}


class ActivitySubmissionAdminOut(BaseModel):
    id: int
    activity_id: int
    activity_title: str
    points: int
    event_title: str
    user_id: int
    user_name: str
    status: str
    text: str | None
    file_type: str | None


def _to_activity_submission_admin_out(row) -> ActivitySubmissionAdminOut:
    submission, activity, event, respondent = row
    return ActivitySubmissionAdminOut(
        id=submission.id,
        activity_id=activity.id,
        activity_title=activity.title,
        points=activity.points,
        event_title=event.title,
        user_id=respondent.id,
        user_name=f"{respondent.first_name} {respondent.last_name or ''}".strip(),
        status=submission.status,
        text=submission.text,
        file_type=submission.file_type,
    )


@router.get("/activities/submissions", response_model=list[ActivitySubmissionAdminOut])
async def list_activity_submissions_endpoint(
    _reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[ActivitySubmissionAdminOut]:
    rows = await event_activity_service.list_reviewable_submissions(session)
    return [_to_activity_submission_admin_out(row) for row in rows]


class ActivityDecisionIn(BaseModel):
    action: Literal["approve", "reject"]


@router.post("/activities/submissions/{submission_id}/decide", response_model=ActivitySubmissionAdminOut)
async def decide_activity_submission_endpoint(
    submission_id: int,
    payload: ActivityDecisionIn,
    reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> ActivitySubmissionAdminOut:
    submission = await session.get(EventActivitySubmission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="submission_not_found")
    activity = await event_activity_service.admin_decide(
        session, submission, approve=payload.action == "approve", reviewer_id=reviewer.id
    )
    if activity is None:
        raise HTTPException(status_code=409, detail="already_reviewed")
    target = await session.get(User, submission.user_id)
    event = await session.get(Event, activity.event_id)
    if bot is not None and target is not None:
        if payload.action == "approve":
            await safe_send(
                bot, target.telegram_id, f"Активность «{activity.title}» одобрена. Начислено: +{activity.points} баллов"
            )
        else:
            await safe_send(
                bot,
                target.telegram_id,
                f"Результат «{activity.title}» пока не подтверждён. Вы можете уточнить причину у команды ЭРА",
            )
    return ActivitySubmissionAdminOut(
        id=submission.id,
        activity_id=activity.id,
        activity_title=activity.title,
        points=activity.points,
        event_title=event.title if event else "",
        user_id=submission.user_id,
        user_name=f"{target.first_name} {target.last_name or ''}".strip() if target else "",
        status=submission.status,
        text=submission.text,
        file_type=submission.file_type,
    )
