from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import (
    AttendanceProof,
    Auction,
    AuctionBid,
    AppSetting,
    Badge,
    Broadcast,
    ChatGreeting,
    Department,
    DepartmentApplication,
    Direction,
    Event,
    EventActivity,
    EventActivitySubmission,
    EventRegistration,
    Office,
    PermissionGrant,
    PointTransaction,
    PortfolioItem,
    Project,
    Proposal,
    Report,
    RewardItem,
    RewardRedemption,
    Task,
    TaskSubmission,
    User,
    UserBadge,
    UserDepartment,
    UserDirection,
    UserQuestion,
    UserOffice,
)
from app.keyboards.admin import (
    admin_activity_keyboard,
    admin_communications_keyboard,
    admin_growth_keyboard,
    admin_panel_keyboard,
    admin_system_keyboard,
    admin_user_actions,
    admin_users_keyboard,
    age_filters_keyboard,
    application_actions,
    applications_keyboard,
    entity_actions,
    event_management_keyboard,
    people_filters_keyboard,
    people_list_keyboard,
    project_review_actions,
    project_snooze_keyboard,
    role_filters_keyboard,
    user_role_keyboard,
    user_status_keyboard,
)
from app.keyboards.participant import main_menu
from app.services.audit_service import audit
from app.services.excel_service import build_analytics_workbook
from app.services.maintenance_service import reset_operational_data, reset_preview
from app.services.notification_service import broadcast, safe_send
from app.services.points_service import add_points, add_portfolio_item, total_points
from app.services.redemption_service import exchange_redemption, reject_redemption
from app.states.admin import (
    AdminAnswerStates,
    AdminAuctionStates,
    AdminBroadcastStates,
    AdminCertificateStates,
    AdminEventActivityStates,
    AdminGrowthStates,
    AdminMaintenanceStates,
    AdminOfficeStates,
    AdminRewardStates,
    AdminRedemptionStates,
    AdminSettingsStates,
    AdminTaskStates,
    AdminPeopleStates,
    AdminPermissionStates,
    AdminReviewStates,
)
from app.utils import texts
from app.utils.constants import (
    ApplicationStatus,
    EventStatus,
    EVENT_STATUS_LABELS,
    ParticipationStatus,
    PROJECT_STATUS_LABELS,
    PERMISSIONS,
    ProjectStatus,
    REPORT_STATUS_LABELS,
    REPORT_TYPE_LABELS,
    RegistrationStatus,
    ROLE_LABELS,
    STATUS_LABELS,
    Role,
)
from app.utils.telegram import send_long_text
from app.utils.validators import clean_text

router = Router(name="admin")

SETTING_LINK_KEYS = {
    "channel": ("Официальный канал", "era_channel_url"),
    "pro": ("Канал ERA PRO", "era_pro_channel_url"),
    "general": ("Общий чат", "general_chat_url"),
    "internal": ("Чат внутренних связей", "internal_department_chat_url"),
    "external": ("Чат внешних связей", "external_department_chat_url"),
    "leaders": ("Чат лидеров", "leaders_chat_url"),
}


def _active_permissions(user: User | None) -> set[str]:
    return {
        grant.permission
        for grant in (getattr(user, "permission_grants", None) or [])
        if grant.is_active
    }


def _is_admin(
    user: User | None,
    settings: Settings,
    telegram_id: int,
    event: Message | CallbackQuery,
) -> bool:
    if telegram_id in settings.admin_ids or (
        user and user.role == Role.ADMIN and not user.is_blocked
    ):
        return True
    if not user or user.is_blocked or user.is_archived:
        return False
    permissions = _active_permissions(user)
    if not permissions:
        return False
    if isinstance(event, Message):
        command = (event.text or "").split(maxsplit=1)[0].split("@", 1)[0]
        command_permissions = {
            "/addpoints": "points.award",
            "/awardbadge": "points.award",
            "/portfolio": "portfolio.review",
            "/setrole": "people.manage",
            "/setstatus": "people.manage",
            "/setsetting": "people.manage",
        }
        required = command_permissions.get(command)
        return required in permissions if required else True
    data = event.data or ""
    if data in {"admin:panel"} or data.startswith("admin:menu:"):
        return True
    rules = (
        (
            (
                "admin:application",
                "admin:approve_user",
                "admin:reject_user",
                "admin:info_user",
            ),
            "applications.review",
        ),
        (
            (
                "admin:participant",
                "admin:people",
                "admin:user",
                "admin:roles",
                "admin:departments",
            ),
            "people.manage",
        ),
        (("admin:project",), "projects.review"),
        (("admin:event", "admin:activity", "admin:proof"), "events.manage"),
        (("admin:task",), "tasks.manage"),
        (
            (
                "admin:points",
                "admin:growth",
                "admin:reward",
                "admin:redemption",
                "admin:auction",
            ),
            "points.award",
        ),
        (("admin:portfolio", "admin:certificate"), "portfolio.review"),
        (
            (
                "admin:broadcast",
                "broadcast:",
                "admin:greeting",
                "admin:question",
                "admin:answer",
            ),
            "broadcasts.create",
        ),
        (("admin:analytics",), "analytics.view"),
        (
            (
                "admin:office",
                "admin:settings",
                "admin:setting_link",
                "admin:bindchat",
            ),
            "people.manage",
        ),
    )
    for prefixes, permission in rules:
        if data.startswith(prefixes):
            return permission in permissions
    return False


async def _guard(
    event: Message | CallbackQuery, user: User | None, settings: Settings
) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
        telegram_id = event.from_user.id
    else:
        message = event
        telegram_id = event.from_user.id
    if not _is_admin(user, settings, telegram_id, event):
        await message.answer(texts.NO_ACCESS)
        return False
    return True


@router.message(Command("admin"))
@router.message(F.text == "⚙️ Управление")
async def admin_command(
    message: Message, user: User | None, settings: Settings, state: FSMContext
) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    await message.answer(texts.ADMIN_PANEL, reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "admin:panel")
async def admin_panel(
    call: CallbackQuery, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.edit_text(texts.ADMIN_PANEL, reply_markup=admin_panel_keyboard())


@router.callback_query(F.data.startswith("admin:menu:"))
async def admin_submenu(
    call: CallbackQuery, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user, settings):
        return
    menus = {
        "users": ("Участники и заявки", admin_users_keyboard()),
        "activity": ("События и проекты", admin_activity_keyboard()),
        "communications": ("Общение и рассылки", admin_communications_keyboard()),
        "growth": ("Баллы и развитие", admin_growth_keyboard()),
        "system": ("Аналитика и настройки", admin_system_keyboard()),
    }
    key = call.data.rsplit(":", 1)[-1]
    item = menus.get(key)
    if item is None:
        await call.message.answer("Раздел не найден.")
        return
    title, keyboard = item
    await call.message.edit_text(title, reply_markup=keyboard)


@router.callback_query(F.data == "admin:applications")
async def applications(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    pending = (
        await session.scalars(
            select(User)
            .where(
                User.application_status.in_(
                    [ApplicationStatus.PENDING, ApplicationStatus.NEEDS_INFO]
                )
            )
            .order_by(User.created_at)
        )
    ).all()
    if not pending:
        await call.message.answer("Новых заявок участников нет.")
        return
    await call.message.answer(
        "Заявки участников:", reply_markup=applications_keyboard(pending)
    )


@router.callback_query(F.data.startswith("admin:application:"))
async def application_detail(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    target = await session.get(User, int(call.data.rsplit(":", 1)[-1]))
    if target is None:
        return
    departments = (
        ", ".join(x.department.name for x in target.departments) or "не выбраны"
    )
    directions = ", ".join(x.direction.name for x in target.directions) or "не выбраны"
    telegram = f"@{target.username}" if target.username else str(target.telegram_id)
    body = f"""📝 Заявка #{target.id}

👤 {target.first_name} {target.last_name or ""}

🎂 Возраст: {target.age or "не указан"}
📍 Город: {target.city or "не указан"}
📱 Телефон: {target.phone or "не указан"}
📧 Email: {target.email or "не указан"}
💬 Telegram: {telegram}

🎓 Учёба / работа
{target.education_work or "не указано"}

💼 Занятие
{target.occupation or "не указано"}

🏛 Департаменты: {departments}
📌 Направления: {directions}
⏳ Доступное время: {target.available_time or "не указано"}
🧭 Желаемый путь: {target.desired_path or "не указан"}

✨ Мотивация
{target.motivation or "не указана"}"""
    await send_long_text(
        call.message, body, reply_markup=application_actions(target.id)
    )


@router.callback_query(F.data.startswith("admin:approve_user:"))
async def approve_user(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    target = await session.get(User, int(call.data.rsplit(":", 1)[-1]))
    if target is None:
        return
    if target.application_status == ApplicationStatus.APPROVED:
        await call.message.answer(
            "Эта заявка уже одобрена — повторное уведомление участнику не отправлено"
        )
        return
    old = target.application_status
    target.application_status = ApplicationStatus.APPROVED
    target.role = Role.PARTICIPANT
    target.participation_status = ParticipationStatus.NEW_MEMBER
    await add_points(
        session,
        user_id=target.id,
        points=5,
        reason="Регистрация в боте",
        approved_by=user.id if user else None,
    )
    await audit(
        session,
        actor_id=user.id if user else None,
        action="user.approved",
        entity_type="user",
        entity_id=target.id,
        old_value={"application_status": old},
        new_value={"application_status": target.application_status},
    )
    await call.message.answer(
        f"Заявка одобрена ✅\n\n{target.first_name} получил доступ к функциям участника"
    )
    await safe_send(
        bot,
        target.telegram_id,
        texts.APPLICATION_APPROVED,
        main_menu(settings.era_channel_url),
    )
    await safe_send(
        bot,
        target.telegram_id,
        "Перед стартом — короткие правила сообщества\n\n" + texts.CHAT_RULES,
    )


async def _start_user_review(
    call: CallbackQuery,
    state: FSMContext,
    action: str,
    target_id: int,
) -> None:
    await state.set_state(AdminReviewStates.comment)
    await state.update_data(
        review_kind="user", review_action=action, review_id=target_id
    )
    await call.message.answer("Напишите комментарий для участника.")


@router.callback_query(F.data.startswith("admin:reject_user:"))
async def reject_user_start(
    call: CallbackQuery, state: FSMContext, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user, settings):
        return
    await _start_user_review(call, state, "reject", int(call.data.rsplit(":", 1)[-1]))


@router.callback_query(F.data.startswith("admin:info_user:"))
async def info_user_start(
    call: CallbackQuery, state: FSMContext, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user, settings):
        return
    await _start_user_review(call, state, "info", int(call.data.rsplit(":", 1)[-1]))


@router.callback_query(F.data == "admin:events")
async def pending_events(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    events = (
        await session.scalars(
            select(Event).order_by(Event.event_date.desc(), Event.event_time).limit(50)
        )
    ).all()
    if not events:
        await call.message.answer("Мероприятий пока нет")
        return
    for event in events:
        actions = (
            entity_actions("event", event.id)
            if event.status == EventStatus.PENDING_APPROVAL
            else event_management_keyboard(event.id, event.status)
        )
        await call.message.answer(
            f"📅 {event.title}\n\n"
            f"{event.event_date:%d.%m.%Y} в {event.event_time:%H:%M}\n"
            f"Место: {event.location}\n"
            f"Статус: {EVENT_STATUS_LABELS.get(event.status, event.status)}",
            reply_markup=actions,
        )


@router.callback_query(F.data.regexp(r"^admin:event:status:[a-z_]+:\d+$"))
async def event_status_change(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, _, status, raw_id = call.data.split(":")
    allowed = {
        EventStatus.REGISTRATION_OPEN,
        EventStatus.REGISTRATION_CLOSED,
        EventStatus.ACTIVE,
        EventStatus.COMPLETED,
    }
    if status not in allowed:
        return
    event = await session.get(Event, int(raw_id))
    if event is None:
        return
    event.status = status
    registrations = (
        await session.scalars(
            select(EventRegistration).where(EventRegistration.event_id == event.id)
        )
    ).all()
    if status == EventStatus.COMPLETED:
        notice = (
            f"Мероприятие «{event.title}» завершено 🌿\n\n"
            "Спасибо, что были частью события. Скоро здесь могут появиться отзыв, фото или другое задание с баллами"
        )
        for registration in registrations:
            target = await session.get(User, registration.user_id)
            if target:
                await safe_send(bot, target.telegram_id, notice)
    await audit(
        session,
        actor_id=user.id if user else None,
        action="event.status_changed",
        entity_type="event",
        entity_id=event.id,
        new_value={"status": status},
    )
    await call.message.answer(
        f"Статус обновлён: {EVENT_STATUS_LABELS.get(status, status)}"
    )


@router.callback_query(F.data.startswith("admin:event:participants:"))
async def event_participants(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    parts = call.data.split(":")
    event_id = int(parts[3])
    page = int(parts[4]) if len(parts) > 4 else 0
    event = await session.get(Event, event_id)
    registrations = (
        await session.scalars(
            select(EventRegistration)
            .where(EventRegistration.event_id == event_id)
            .order_by(EventRegistration.created_at)
        )
    ).all()
    if not registrations:
        await call.message.answer("На мероприятие пока никто не зарегистрирован")
        return
    page_size = 20
    visible = registrations[page * page_size : (page + 1) * page_size]
    rows = []
    for registration in visible:
        target = await session.get(User, registration.user_id)
        marker = "✅" if registration.status == RegistrationStatus.ATTENDED else "▫️"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker} {target.first_name} {target.last_name or ''}".strip(),
                    callback_data=f"admin:event:attend:{event_id}:{target.id}",
                )
            ]
        )
    navigation = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="←",
                callback_data=f"admin:event:participants:{event_id}:{page - 1}",
            )
        )
    if (page + 1) * page_size < len(registrations):
        navigation.append(
            InlineKeyboardButton(
                text="→",
                callback_data=f"admin:event:participants:{event_id}:{page + 1}",
            )
        )
    if navigation:
        rows.append(navigation)
    rows.append(
        [InlineKeyboardButton(text="← К мероприятиям", callback_data="admin:events")]
    )
    await call.message.answer(
        f"👥 {event.title}\n\nНажмите на участника, чтобы подтвердить присутствие",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.regexp(r"^admin:event:attend:\d+:\d+$"))
async def event_attendance_confirm(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, _, raw_event_id, raw_user_id = call.data.split(":")
    event_id, target_id = int(raw_event_id), int(raw_user_id)
    registration = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == target_id,
        )
    )
    if registration is None:
        return
    if registration.status == RegistrationStatus.ATTENDED:
        await call.message.answer(
            "Участие уже подтверждено — повторно баллы не начислены"
        )
        return
    event = await session.get(Event, event_id)
    registration.status = RegistrationStatus.ATTENDED
    await add_points(
        session,
        user_id=target_id,
        points=event.points_for_visit,
        reason=f"Участие в мероприятии: {event.title}",
        approved_by=user.id if user else None,
        related_event_id=event.id,
    )
    await add_portfolio_item(
        session,
        user_id=target_id,
        title=f"Участие: {event.title}",
        item_type="event",
        description="Участие подтверждено командой ЭРА",
        issued_by=user.id if user else None,
        related_event_id=event.id,
    )
    target = await session.get(User, target_id)
    await call.message.answer(
        "Участие подтверждено, баллы и запись в портфолио добавлены"
    )
    if target:
        await safe_send(
            bot,
            target.telegram_id,
            f"Ваше участие в «{event.title}» подтверждено — начислено {event.points_for_visit} баллов",
        )


@router.callback_query(F.data == "admin:projects")
async def pending_projects(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    projects = (
        await session.scalars(
            select(Project)
            .where(
                Project.status.in_(
                    [
                        ProjectStatus.PENDING_REVIEW,
                        ProjectStatus.INITIAL_REVIEW,
                        ProjectStatus.VENUE_REVIEW,
                    ]
                )
            )
            .order_by(Project.submitted_at, Project.created_at)
        )
    ).all()
    if not projects:
        await call.message.answer("Проектов на рассмотрении нет.")
        return
    for project in projects:
        author = await session.get(User, project.author_id)
        data = project.form_data or {}
        author_name = (
            f"{author.first_name} {author.last_name or ''}".strip()
            if author
            else f"ID {project.author_id}"
        )
        username = (
            f"@{author.username}" if author and author.username else "без username"
        )
        body = f"""💡 Проект #{project.id}

{project.title}

Автор: {author_name} ({username})
Статус: {PROJECT_STATUS_LABELS.get(project.status, project.status)}

Суть
{project.short_description}

Аудитория
{data.get("target_audience", project.target_audience or "не указана")}

Дата и время: {data.get("proposed_date", "не указана")}, {data.get("proposed_time", "не указано")}
Площадка: {data.get("venue_request", "не указана")}
Бюджет: {data.get("budget", "не указан")}"""
        await send_long_text(
            call.message,
            body,
            reply_markup=project_review_actions(project.id, project.status),
        )


@router.callback_query(F.data == "admin:attendance")
async def pending_attendance(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    proofs = (
        await session.scalars(
            select(AttendanceProof)
            .where(AttendanceProof.status == "pending")
            .order_by(AttendanceProof.created_at)
        )
    ).all()
    if not proofs:
        await call.message.answer("Селфи на проверке нет.")
        return
    for proof in proofs:
        event = await session.get(Event, proof.event_id)
        target = await session.get(User, proof.user_id)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Подтвердить",
                        callback_data=f"admin:proof:approve:{proof.id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Отклонить", callback_data=f"admin:proof:reject:{proof.id}"
                    )
                ],
            ]
        )
        caption = (
            f"Селфи #{proof.id}\n{target.first_name if target else 'Участник'}\n"
            f"Мероприятие: {event.title if event else proof.event_id}"
        )
        await call.message.answer_photo(
            proof.photo_file_id, caption=caption, reply_markup=keyboard
        )


@router.callback_query(F.data == "admin:event_activities")
async def event_activity_submissions(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    submissions = (
        await session.scalars(
            select(EventActivitySubmission)
            .where(EventActivitySubmission.status == "pending")
            .order_by(EventActivitySubmission.created_at)
            .limit(50)
        )
    ).all()
    if not submissions:
        await call.message.answer(
            "✨ Активности после мероприятий\n\nНовых ответов на проверке нет",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="➕ Создать активность",
                            callback_data="admin:activity:new",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="← Назад", callback_data="admin:menu:activity"
                        )
                    ],
                ]
            ),
        )
        return
    await call.message.answer(
        "Ниже — ответы на проверке",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="➕ Создать активность", callback_data="admin:activity:new"
                    )
                ]
            ]
        ),
    )
    for submission in submissions:
        activity = await session.get(EventActivity, submission.activity_id)
        target = await session.get(User, submission.user_id)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"Принять · +{activity.points}",
                        callback_data=f"admin:activity:approve:{submission.id}",
                    ),
                    InlineKeyboardButton(
                        text="Не принимать",
                        callback_data=f"admin:activity:reject:{submission.id}",
                    ),
                ]
            ]
        )
        body = (
            f"✨ {activity.title}\n\n"
            f"Участник: {target.first_name if target else submission.user_id} "
            f"{target.last_name or '' if target else ''}\n"
            f"Награда: {activity.points} баллов\n\n"
            f"{submission.text or 'Материал прикреплён файлом'}"
        )
        await call.message.answer(body, reply_markup=keyboard)


@router.callback_query(F.data == "admin:activity:new")
async def activity_new_choose_event(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    events = (
        await session.scalars(
            select(Event)
            .where(
                Event.status.in_(
                    [EventStatus.PUBLISHED, EventStatus.ACTIVE, EventStatus.COMPLETED]
                )
            )
            .order_by(Event.event_date.desc())
            .limit(30)
        )
    ).all()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{event.title[:40]} · {event.event_date:%d.%m}",
                    callback_data=f"admin:activity:event:{event.id}",
                )
            ]
            for event in events
        ]
        + [
            [
                InlineKeyboardButton(
                    text="← Назад", callback_data="admin:event_activities"
                )
            ]
        ]
    )
    await call.message.answer("Для какого мероприятия?", reply_markup=keyboard)


@router.callback_query(F.data.startswith("admin:activity:event:"))
async def activity_new_title(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminEventActivityStates.title)
    await state.update_data(activity_event_id=int(call.data.rsplit(":", 1)[-1]))
    await call.message.answer(
        "Как называется активность? Например: «Поделитесь впечатлением»"
    )


@router.message(AdminEventActivityStates.title)
async def activity_title(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 255)
    if not value:
        return
    await state.update_data(activity_title=value)
    await state.set_state(AdminEventActivityStates.description)
    await message.answer("Что нужно сделать участнику?")


@router.message(AdminEventActivityStates.description)
async def activity_description(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 2000)
    if not value:
        return
    await state.update_data(activity_description=value)
    await state.set_state(AdminEventActivityStates.submission_type)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Текст / отзыв", callback_data="admin:activity:type:text"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Фотография", callback_data="admin:activity:type:photo"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Видео", callback_data="admin:activity:type:video"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Файл", callback_data="admin:activity:type:file"
                )
            ],
        ]
    )
    await message.answer("В каком формате принять результат?", reply_markup=keyboard)


@router.callback_query(
    AdminEventActivityStates.submission_type,
    F.data.startswith("admin:activity:type:"),
)
async def activity_type(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(activity_type=call.data.rsplit(":", 1)[-1])
    await state.set_state(AdminEventActivityStates.points)
    await call.message.answer("Сколько баллов начислить после проверки?")


@router.message(AdminEventActivityStates.points)
async def activity_points(message: Message, state: FSMContext) -> None:
    try:
        points = int((message.text or "").strip())
        if not 0 <= points <= 1000:
            raise ValueError
    except ValueError:
        await message.answer("Введите число от 0 до 1000")
        return
    await state.update_data(activity_points=points)
    await state.set_state(AdminEventActivityStates.deadline)
    await message.answer("До какого срока принимать ответы? Формат: ДД.ММ.ГГГГ ЧЧ:ММ")


@router.message(AdminEventActivityStates.deadline)
async def activity_finish(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(message, user, settings):
        return
    try:
        deadline = datetime.strptime(message.text or "", "%d.%m.%Y %H:%M").replace(
            tzinfo=ZoneInfo(settings.timezone)
        )
    except ValueError:
        await message.answer("Проверьте формат: ДД.ММ.ГГГГ ЧЧ:ММ")
        return
    data = await state.get_data()
    activity = EventActivity(
        event_id=data["activity_event_id"],
        title=data["activity_title"],
        description=data["activity_description"],
        submission_type=data["activity_type"],
        points=data["activity_points"],
        deadline=deadline,
    )
    session.add(activity)
    event = await session.get(Event, activity.event_id)
    registrations = (
        await session.scalars(
            select(EventRegistration).where(
                EventRegistration.event_id == activity.event_id
            )
        )
    ).all()
    await state.clear()
    await message.answer("Активность опубликована участникам мероприятия")
    for registration in registrations:
        target = await session.get(User, registration.user_id)
        if target:
            await safe_send(
                bot,
                target.telegram_id,
                f"✨ Новая активность после «{event.title}»\n\n"
                f"{activity.title}\n{activity.description}\n\n"
                f"Награда: {activity.points} баллов\n"
                "Откройте «Мой путь» → «Мои мероприятия», чтобы отправить результат",
            )


@router.callback_query(F.data.regexp(r"^admin:activity:(approve|reject):\d+$"))
async def event_activity_decide(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, action, raw_id = call.data.split(":")
    submission = await session.get(EventActivitySubmission, int(raw_id))
    if submission is None or submission.status != "pending":
        await call.message.answer("Ответ уже проверен")
        return
    activity = await session.get(EventActivity, submission.activity_id)
    target = await session.get(User, submission.user_id)
    submission.status = "approved" if action == "approve" else "rejected"
    submission.reviewed_by = user.id if user else None
    if action == "approve":
        submission.points_awarded = activity.points
        await add_points(
            session,
            user_id=submission.user_id,
            points=activity.points,
            reason=f"Активность после мероприятия: {activity.title}",
            approved_by=user.id if user else None,
            related_event_id=activity.event_id,
        )
    await call.message.answer(
        "Ответ принят и баллы начислены"
        if action == "approve"
        else "Ответ отмечен как неподтверждённый"
    )
    if target:
        notice = (
            f"Ваш результат «{activity.title}» принят — начислено {activity.points} баллов"
            if action == "approve"
            else f"Результат «{activity.title}» пока не подтверждён. Вы можете уточнить причину у команды ЭРА"
        )
        await safe_send(bot, target.telegram_id, notice)


@router.callback_query(F.data.startswith("admin:proof:approve:"))
async def approve_proof(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    proof = await session.get(AttendanceProof, int(call.data.rsplit(":", 1)[-1]))
    if proof is None or proof.status != "pending":
        return
    event = await session.get(Event, proof.event_id)
    target = await session.get(User, proof.user_id)
    proof.status = "approved"
    proof.reviewed_by = user.id if user else None
    registration = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == proof.event_id,
            EventRegistration.user_id == proof.user_id,
        )
    )
    if registration:
        registration.status = RegistrationStatus.ATTENDED
    points = (event.points_for_visit if event else 5) + 5
    await add_points(
        session,
        user_id=proof.user_id,
        points=points,
        reason="Подтверждённое участие в мероприятии",
        approved_by=user.id if user else None,
        related_event_id=proof.event_id,
    )
    await add_portfolio_item(
        session,
        user_id=proof.user_id,
        title=f"Участие: {event.title if event else 'мероприятие ЭРА'}",
        item_type="event",
        description="Участие подтверждено командой ЭРА",
        issued_by=user.id if user else None,
        related_event_id=proof.event_id,
    )
    await call.message.answer("Участие подтверждено.")
    if target:
        feedback_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Оставить обратную связь",
                        callback_data=f"feedback:start:{proof.event_id}",
                    )
                ]
            ]
        )
        await safe_send(
            bot,
            target.telegram_id,
            texts.SELFIE_APPROVED.format(points=points),
            reply_markup=feedback_keyboard,
        )


@router.callback_query(F.data.startswith("admin:proof:reject:"))
async def reject_proof_start(
    call: CallbackQuery,
    state: FSMContext,
    user: User | None,
    settings: Settings,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminReviewStates.comment)
    await state.update_data(
        review_kind="proof",
        review_action="reject",
        review_id=int(call.data.rsplit(":", 1)[-1]),
    )
    await call.message.answer("Напишите причину отклонения селфи.")


@router.callback_query(F.data.startswith("admin:event:approve:"))
async def approve_entity(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, kind, _, raw_id = call.data.split(":")
    entity_id = int(raw_id)
    entity = await session.get(Event, entity_id)
    if entity is None:
        return
    entity.status = EventStatus.PUBLISHED
    entity.approved_by = user.id if user else None
    await audit(
        session,
        actor_id=user.id if user else None,
        action=f"{kind}.approved",
        entity_type=kind,
        entity_id=entity_id,
    )
    await call.message.answer("Решение сохранено: одобрено.")
    owner_id = entity.created_by
    owner = await session.get(User, owner_id)
    if owner:
        notice = f"Мероприятие «{entity.title}» одобрено и опубликовано."
        await safe_send(bot, owner.telegram_id, notice)
    if settings.general_chat_id:
        await safe_send(
            bot,
            settings.general_chat_id,
            f"Новое мероприятие ЭРА\n\n{entity.title}\n"
            f"{entity.event_date:%d.%m.%Y} в {entity.event_time:%H:%M}\n"
            f"Место: {entity.location}\n\n{entity.description}",
        )


@router.callback_query(F.data.regexp(r"^admin:project:review:[a-z_]+:\d+$"))
async def project_review_start(
    call: CallbackQuery,
    state: FSMContext,
    user: User | None,
    settings: Settings,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, _, action, raw_id = call.data.split(":")
    await state.set_state(AdminReviewStates.comment)
    await state.update_data(
        review_kind="project", review_action=action, review_id=int(raw_id)
    )
    prompts = {
        "initial_accept": "Напишите, что уже принято в работу и что нужно уточнить по площадке",
        "venue_approve": "Напишите итог по площадке и важные условия проведения",
        "postpone": "Укажите причину и ориентир, когда вернуться к проекту",
        "revise": "Напишите конкретно, что автору нужно доработать",
        "reject": "Объясните решение уважительно и по существу",
    }
    await call.message.answer(
        f"💬 {prompts.get(action, 'Добавьте комментарий к решению')}\n\n"
        "Комментарий обязателен — автор получит его вместе с решением"
    )


@router.callback_query(F.data.startswith("admin:project:snooze:"))
async def project_snooze(
    call: CallbackQuery, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user, settings):
        return
    project_id = int(call.data.rsplit(":", 1)[-1])
    await call.message.answer(
        "Когда снова напомнить об утверждении площадки?",
        reply_markup=project_snooze_keyboard(project_id),
    )


@router.callback_query(F.data.regexp(r"^admin:project:snooze_set:\d+:\d+$"))
async def project_snooze_set(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, _, raw_id, raw_days = call.data.split(":")
    project = await session.get(Project, int(raw_id))
    if project is None or project.status != ProjectStatus.VENUE_REVIEW:
        await call.message.answer("Проект уже перешёл на другой этап")
        return
    days = int(raw_days)
    project.venue_remind_at = datetime.now().astimezone() + timedelta(days=days)
    await call.message.answer(f"Хорошо, напомню через {days} дн.")


@router.callback_query(F.data.regexp(r"^admin:(event|project):(revise|reject):\d+$"))
async def review_entity_start(
    call: CallbackQuery,
    state: FSMContext,
    user: User | None,
    settings: Settings,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, kind, action, raw_id = call.data.split(":")
    await state.set_state(AdminReviewStates.comment)
    await state.update_data(
        review_kind=kind, review_action=action, review_id=int(raw_id)
    )
    await call.message.answer("Напишите комментарий к решению.")


@router.message(AdminReviewStates.comment)
async def review_comment(
    message: Message,
    state: FSMContext,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(message, user, settings):
        return
    comment = clean_text(message.text or "", 2000)
    if not comment:
        await message.answer(texts.INVALID_INPUT)
        return
    data = await state.get_data()
    kind, action, entity_id = (
        data["review_kind"],
        data["review_action"],
        data["review_id"],
    )
    if kind == "user":
        target = await session.get(User, entity_id)
        if target:
            target.application_status = (
                ApplicationStatus.REJECTED
                if action == "reject"
                else ApplicationStatus.NEEDS_INFO
            )
            notice = (
                f"{texts.APPLICATION_REJECTED}\n\nКомментарий: {comment}"
                if action == "reject"
                else texts.APPLICATION_NEEDS_INFO.format(comment=comment)
            )
            await safe_send(bot, target.telegram_id, notice)
    elif kind == "proof":
        proof = await session.get(AttendanceProof, entity_id)
        if proof:
            proof.status = "rejected"
            proof.reviewed_by = user.id if user else None
            proof.admin_comment = comment
            target = await session.get(User, proof.user_id)
            if target:
                await safe_send(
                    bot,
                    target.telegram_id,
                    texts.SELFIE_REJECTED.format(comment=comment),
                )
    else:
        entity = await session.get(Event if kind == "event" else Project, entity_id)
        if entity:
            entity.admin_comment = comment
            if kind == "project":
                owner = await session.get(User, entity.author_id)
                notices = {
                    "initial_accept": (
                        ProjectStatus.VENUE_REVIEW,
                        "Ваш проект прошёл первичную проверку и теперь согласовывается с площадкой",
                    ),
                    "venue_approve": (
                        ProjectStatus.APPROVED,
                        "Проект одобрен — можно переходить к подготовке",
                    ),
                    "postpone": (
                        ProjectStatus.POSTPONED,
                        "Проект пока перенесён, но остаётся в системе",
                    ),
                    "revise": (
                        ProjectStatus.NEEDS_REVISION,
                        "Проект возвращён Вам на доработку",
                    ),
                    "reject": (
                        ProjectStatus.REJECTED,
                        "Сейчас проект не может быть одобрен",
                    ),
                }
                new_status, notice = notices.get(
                    action,
                    (ProjectStatus.NEEDS_REVISION, "По проекту принято решение"),
                )
                previous_status = entity.status
                entity.status = new_status
                if action == "initial_accept":
                    entity.venue_status = "pending"
                    entity.venue_comment = comment
                    entity.venue_reminder_count = 0
                    entity.venue_remind_at = datetime.now().astimezone() + timedelta(
                        days=1
                    )
                elif action == "venue_approve":
                    entity.venue_status = "approved"
                    entity.venue_comment = comment
                    entity.venue_remind_at = None
                    if previous_status != ProjectStatus.APPROVED:
                        await add_points(
                            session,
                            user_id=entity.author_id,
                            points=30,
                            reason=f"Одобренный проект: {entity.title}",
                            approved_by=user.id if user else None,
                            related_project_id=entity.id,
                        )
                        await add_portfolio_item(
                            session,
                            user_id=entity.author_id,
                            title=f"Автор проекта: {entity.title}",
                            item_type="project",
                            description=entity.short_description,
                            issued_by=user.id if user else None,
                            related_project_id=entity.id,
                        )
                else:
                    entity.venue_remind_at = None
                if owner:
                    await safe_send(
                        bot,
                        owner.telegram_id,
                        f"💡 {notice}\n\nПроект: {entity.title}\n\n"
                        f"Комментарий команды ЭРА:\n{comment}\n\n"
                        "Откройте раздел «Мои проекты», чтобы увидеть актуальный статус",
                    )
            else:
                entity.status = (
                    EventStatus.DRAFT if action == "revise" else EventStatus.CANCELLED
                )
                owner = await session.get(User, entity.created_by)
                if owner:
                    await safe_send(
                        bot,
                        owner.telegram_id,
                        f"Решение по мероприятию «{entity.title}»: {action}. Комментарий: {comment}",
                    )
    await audit(
        session,
        actor_id=user.id if user else None,
        action=f"{kind}.{action}",
        entity_type=kind,
        entity_id=entity_id,
        new_value={"comment": comment},
    )
    await state.clear()
    await message.answer("Решение сохранено и отправлено.")


@router.callback_query(F.data == "admin:questions")
async def questions(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    items = (
        await session.scalars(
            select(UserQuestion)
            .where(UserQuestion.status == "new")
            .order_by(UserQuestion.created_at)
        )
    ).all()
    if not items:
        await call.message.answer("Новых вопросов нет.")
        return
    for question in items:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Ответить", callback_data=f"admin:answer:{question.id}"
                    )
                ]
            ]
        )
        await call.message.answer(
            f"Вопрос #{question.id}\n\n{question.text}", reply_markup=keyboard
        )


@router.callback_query(F.data.startswith("admin:answer:"))
async def answer_start(
    call: CallbackQuery,
    state: FSMContext,
    user: User | None,
    settings: Settings,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminAnswerStates.answer)
    await state.update_data(question_id=int(call.data.rsplit(":", 1)[-1]))
    await call.message.answer("Напишите ответ участнику.")


@router.message(AdminAnswerStates.answer)
async def answer_finish(
    message: Message,
    state: FSMContext,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(message, user, settings):
        return
    answer = clean_text(message.text or "", 3000)
    if not answer:
        await message.answer(texts.INVALID_INPUT)
        return
    question = await session.get(UserQuestion, (await state.get_data())["question_id"])
    if question:
        question.admin_answer = answer
        question.answered_by = user.id if user else None
        question.status = "answered"
        target = await session.get(User, question.user_id)
        if target:
            await safe_send(
                bot, target.telegram_id, texts.QUESTION_ANSWER.format(answer=answer)
            )
    await state.clear()
    await message.answer("Ответ отправлен.")


@router.callback_query(F.data == "admin:portfolio")
async def portfolio_help(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.answer(
        "🎓 Портфолио и сертификаты",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Сертификат участнику",
                        callback_data="admin:certificate:person",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Сертификат всем на мероприятии",
                        callback_data="admin:certificate:event",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="← Назад", callback_data="admin:menu:growth"
                    )
                ],
            ]
        ),
    )
    pending = (
        await session.scalars(
            select(PortfolioItem)
            .where(PortfolioItem.status == "pending")
            .order_by(PortfolioItem.created_at)
            .limit(30)
        )
    ).all()
    if not pending:
        await call.message.answer(
            "Новых материалов на проверке нет\n\n"
            "Здесь будут сертификаты и достижения, которые участники загрузили сами"
        )
        return
    for item in pending:
        target = await session.get(User, item.user_id)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Подтвердить",
                        callback_data=f"admin:portfolio:approve:{item.id}",
                    ),
                    InlineKeyboardButton(
                        text="Отклонить",
                        callback_data=f"admin:portfolio:reject:{item.id}",
                    ),
                ]
            ]
        )
        caption = (
            f"📎 Достижение #{item.id}\n\n"
            f"Участник: {target.first_name if target else item.user_id} "
            f"{target.last_name or '' if target else ''}\n"
            f"Название: {item.title}\n\n{item.description or ''}"
        )
        if item.file_id:
            try:
                await call.message.answer_document(item.file_id, caption=caption, reply_markup=keyboard)
            except Exception:
                await call.message.answer_photo(item.file_id, caption=caption, reply_markup=keyboard)
        else:
            await call.message.answer(caption, reply_markup=keyboard)


@router.callback_query(F.data.regexp(r"^admin:portfolio:(approve|reject):\d+$"))
async def portfolio_decide(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, action, raw_id = call.data.split(":")
    item = await session.get(PortfolioItem, int(raw_id))
    if item is None or item.status != "pending":
        await call.message.answer("Материал уже проверен")
        return
    item.status = "verified" if action == "approve" else "rejected"
    item.verified_by = user.id if user else None
    target = await session.get(User, item.user_id)
    await call.message.answer(
        "Достижение добавлено в портфолио"
        if action == "approve"
        else "Материал отклонён"
    )
    if target:
        await safe_send(
            bot,
            target.telegram_id,
            f"Ваш материал «{item.title}» "
            + (
                "подтверждён и появился в портфолио"
                if action == "approve"
                else "не прошёл проверку. Вы можете загрузить более подробное подтверждение"
            ),
        )


@router.callback_query(F.data == "admin:certificate:person")
async def certificate_person_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminCertificateStates.person)
    await state.update_data(certificate_mode="person")
    await call.message.answer(
        "Кому добавить сертификат? Напишите имя, фамилию, @username или Telegram ID"
    )


@router.message(AdminCertificateStates.person)
async def certificate_person_find(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    query = clean_text(message.text or "", 150).lstrip("@").lower()
    conditions = [
        User.first_name.ilike(f"%{query}%"),
        User.last_name.ilike(f"%{query}%"),
        User.username.ilike(f"%{query}%"),
    ]
    if query.isdigit():
        conditions.append(User.telegram_id == int(query))
    targets = (
        await session.scalars(select(User).where(or_(*conditions)).limit(8))
    ).all()
    if not targets:
        await message.answer("Участник не найден")
        return
    await message.answer(
        "Выберите участника",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"{target.first_name} {target.last_name or ''}".strip(),
                        callback_data=f"admin:certificate:target:{target.id}",
                    )
                ]
                for target in targets
            ]
        ),
    )


@router.callback_query(
    AdminCertificateStates.person, F.data.startswith("admin:certificate:target:")
)
async def certificate_person_select(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(certificate_target_id=int(call.data.rsplit(":", 1)[-1]))
    await state.set_state(AdminCertificateStates.title)
    await call.message.answer("Название сертификата или достижения")


@router.callback_query(F.data == "admin:certificate:event")
async def certificate_event_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    events = (
        await session.scalars(select(Event).order_by(Event.event_date.desc()).limit(30))
    ).all()
    await state.set_state(AdminCertificateStates.person)
    await state.update_data(certificate_mode="event")
    await call.message.answer(
        "Участникам какого мероприятия добавить сертификат?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"{event.title[:40]} · {event.event_date:%d.%m}",
                        callback_data=f"admin:certificate:event_select:{event.id}",
                    )
                ]
                for event in events
            ]
        ),
    )


@router.callback_query(
    AdminCertificateStates.person,
    F.data.startswith("admin:certificate:event_select:"),
)
async def certificate_event_select(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(certificate_event_id=int(call.data.rsplit(":", 1)[-1]))
    await state.set_state(AdminCertificateStates.title)
    await call.message.answer("Название сертификата")


@router.message(AdminCertificateStates.title)
async def certificate_title(message: Message, state: FSMContext) -> None:
    title = clean_text(message.text or "", 255)
    if not title:
        return
    await state.update_data(certificate_title=title)
    await state.set_state(AdminCertificateStates.file)
    await message.answer("Прикрепите сертификат файлом или фотографией")


@router.message(AdminCertificateStates.file, F.document | F.photo)
async def certificate_file(
    message: Message,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:
    if not await _guard(message, user, settings):
        return
    data = await state.get_data()
    file_id = (
        message.document.file_id if message.document else message.photo[-1].file_id
    )
    if data["certificate_mode"] == "person":
        target_ids = [int(data["certificate_target_id"])]
        related_event_id = None
    else:
        related_event_id = int(data["certificate_event_id"])
        target_ids = list(
            (
                await session.scalars(
                    select(EventRegistration.user_id).where(
                        EventRegistration.event_id == related_event_id,
                        EventRegistration.status == RegistrationStatus.ATTENDED,
                    )
                )
            ).all()
        )
    for target_id in target_ids:
        await add_portfolio_item(
            session,
            user_id=target_id,
            title=data["certificate_title"],
            item_type="certificate",
            description="Сертификат подтверждён командой ЭРА",
            issued_by=user.id if user else None,
            file_id=file_id,
            related_event_id=related_event_id,
            status="verified",
            verified_by=user.id if user else None,
        )
        target = await session.get(User, target_id)
        if target:
            await bot.send_document(
                target.telegram_id,
                file_id,
                caption=f"В Ваше портфолио добавлен сертификат «{data['certificate_title']}» 🎓",
            )
    await state.clear()
    await message.answer(f"Сертификат добавлен: {len(target_ids)} участникам")


@router.message(AdminCertificateStates.file)
async def certificate_file_wrong(message: Message) -> None:
    await message.answer("Прикрепите документ или фотографию")


@router.callback_query(F.data == "admin:rewards")
async def rewards_admin_menu(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    rewards = (
        await session.scalars(
            select(RewardItem)
            .where(RewardItem.is_active.is_(True))
            .order_by(RewardItem.point_cost)
        )
    ).all()
    redemptions = int(
        await session.scalar(
            select(func.count())
            .select_from(RewardRedemption)
            .where(RewardRedemption.status == "pending")
        )
        or 0
    )
    rows = [
        [
            InlineKeyboardButton(
                text="➕ Новая возможность", callback_data="admin:reward:new"
            ),
            InlineKeyboardButton(
                text=f"Заявки · {redemptions}", callback_data="admin:reward:redemptions"
            ),
        ]
    ]
    rows.extend(
        [
            InlineKeyboardButton(
                text=f"{item.name} · {item.point_cost}",
                callback_data=f"admin:reward:disable:{item.id}",
            )
        ]
        for item in rewards
    )
    rows.append(
        [InlineKeyboardButton(text="← Назад", callback_data="admin:menu:growth")]
    )
    await call.message.answer(
        "🎁 Каталог возможностей\n\nНажмите на активную позицию, чтобы убрать её из каталога",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "admin:reward:new")
async def reward_new_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminRewardStates.name)
    await call.message.answer("Как называется возможность или награда?")


@router.message(AdminRewardStates.name)
async def reward_new_name(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 255)
    if not value:
        return
    await state.update_data(reward_name=value)
    await state.set_state(AdminRewardStates.description)
    await message.answer("Что получит участник? Опишите коротко и конкретно")


@router.message(AdminRewardStates.description)
async def reward_new_description(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 2000)
    if not value:
        return
    await state.update_data(reward_description=value)
    await state.set_state(AdminRewardStates.cost)
    await message.answer("Сколько баллов стоит эта возможность?")


@router.message(AdminRewardStates.cost)
async def reward_new_cost(message: Message, state: FSMContext) -> None:
    try:
        value = int((message.text or "").strip())
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите положительное целое число")
        return
    await state.update_data(reward_cost=value)
    await state.set_state(AdminRewardStates.quantity)
    await message.answer(
        "Сколько экземпляров доступно? Отправьте 0, если без ограничения"
    )


@router.message(AdminRewardStates.quantity)
async def reward_new_finish(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(message, user, settings):
        return
    try:
        quantity = int((message.text or "").strip())
        if quantity < 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите 0 или положительное целое число")
        return
    data = await state.get_data()
    session.add(
        RewardItem(
            name=data["reward_name"],
            description=data["reward_description"],
            point_cost=data["reward_cost"],
            quantity=quantity or None,
            created_by=user.id if user else 1,
        )
    )
    await state.clear()
    await message.answer("Возможность опубликована в каталоге")


@router.callback_query(F.data.startswith("admin:reward:disable:"))
async def reward_disable(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    reward = await session.get(RewardItem, int(call.data.rsplit(":", 1)[-1]))
    if reward:
        reward.is_active = False
    await call.message.answer("Позиция скрыта из каталога, история обменов сохранена")


def _redemption_keyboard(item: RewardRedemption) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="💬 Ответить пользователю",
                callback_data=f"admin:redemption:answer:{item.id}",
            )
        ]
    ]
    if item.status == "answered":
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Обменять и списать баллы",
                    callback_data=f"admin:redemption:exchange:{item.id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="❌ Отклонить без списания",
                callback_data=f"admin:redemption:reject:{item.id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "admin:reward:redemptions")
async def reward_redemptions(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    items = (
        await session.scalars(
            select(RewardRedemption)
            .where(RewardRedemption.status.in_(["pending", "answered"]))
            .order_by(RewardRedemption.created_at)
        )
    ).all()
    if not items:
        await call.message.answer("Новых заявок на обмен нет")
        return
    for item in items:
        reward = await session.get(RewardItem, item.reward_id)
        target = await session.get(User, item.user_id)
        if reward is None or target is None:
            continue
        status = "ожидает ответа" if item.status == "pending" else "ответ отправлен"
        answer = (
            f"\nОтвет участнику: {item.admin_comment}"
            if item.admin_comment
            else ""
        )
        await call.message.answer(
            f"🎁 {reward.name}\n\n"
            f"Участник: {target.first_name} {target.last_name or ''}\n"
            f"Стоимость: {item.points_spent} баллов\n"
            f"Статус: {status}{answer}\n\n"
            "Баллы ещё не списаны",
            reply_markup=_redemption_keyboard(item),
        )


@router.callback_query(F.data.startswith("admin:redemption:answer:"))
async def redemption_answer_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    item = await session.get(RewardRedemption, int(call.data.rsplit(":", 1)[-1]))
    if item is None or item.status not in {"pending", "answered"}:
        await call.message.answer("Эта заявка уже закрыта")
        return
    await state.set_state(AdminRedemptionStates.answer)
    await state.update_data(redemption_id=item.id)
    await call.message.answer(
        "Напишите участнику ответ по этой возможности\n\n"
        "После успешной отправки ответа появится кнопка окончательного обмена"
    )


@router.message(AdminRedemptionStates.answer)
async def redemption_answer_save(
    message: Message,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:
    if not await _guard(message, user, settings):
        return
    answer = clean_text(message.text or "", 2000)
    if not answer:
        await message.answer("Напишите ответ текстом")
        return
    data = await state.get_data()
    item = await session.get(RewardRedemption, int(data["redemption_id"]))
    if item is None or item.status not in {"pending", "answered"}:
        await state.clear()
        await message.answer("Эта заявка уже закрыта")
        return
    reward = await session.get(RewardItem, item.reward_id)
    target = await session.get(User, item.user_id)
    if reward is None or target is None:
        await state.clear()
        await message.answer("Не удалось найти возможность или участника")
        return
    delivered = await safe_send(
        bot,
        target.telegram_id,
        f"🎁 Ответ по возможности «{reward.name}»\n\n{answer}\n\n"
        "Баллы пока не списаны — окончательное решение об обмене ещё не принято",
    )
    if not delivered:
        await state.clear()
        await message.answer(
            "Ответ не доставлен. Списание недоступно — попробуйте связаться с участником позже"
        )
        return
    item.status = "answered"
    item.admin_comment = answer
    item.reviewed_by = user.id if user else None
    await state.clear()
    await message.answer(
        "Ответ доставлен. Теперь можно подтвердить обмен и списать баллы один раз",
        reply_markup=_redemption_keyboard(item),
    )


@router.callback_query(
    F.data.regexp(r"^admin:redemption:(exchange|approve|reject):\d+$")
)
async def redemption_decide(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, action, raw_id = call.data.split(":")
    admin_id = user.id if user else None

    if action == "reject":
        result = await reject_redemption(
            session, redemption_id=int(raw_id), admin_id=admin_id
        )
        if result.code == "rejected":
            await call.message.answer(
                "Заявка отклонена без списания баллов"
            )
            if result.redemption and result.reward:
                target = await session.get(User, result.redemption.user_id)
                if target:
                    await safe_send(
                        bot,
                        target.telegram_id,
                        f"Заявка на «{result.reward.name}» отклонена. "
                        "Баллы с Вашего баланса не списывались",
                    )
            return
        await call.message.answer("Эта заявка уже обработана")
        return

    # Legacy approve buttons are intentionally routed through the new safe exchange.
    result = await exchange_redemption(
        session, redemption_id=int(raw_id), admin_id=admin_id
    )
    messages = {
        "answer_required": (
            "Сначала ответьте участнику — до этого списывать баллы нельзя"
        ),
        "already_exchanged": "Обмен уже выполнен — повторного списания не было",
        "already_closed": "Эта заявка уже закрыта",
        "not_found": "Заявка не найдена",
        "reward_missing": "Возможность больше не найдена",
        "unavailable": "Возможность закончилась — баллы не списаны",
        "insufficient_points": (
            "У участника уже недостаточно баллов — обмен не выполнен"
        ),
    }
    if result.code != "exchanged":
        await call.message.answer(messages.get(result.code, "Обмен не выполнен"))
        return

    target = await session.get(User, result.redemption.user_id)
    balance = await total_points(session, result.redemption.user_id)
    await call.message.answer(
        f"Обмен подтверждён. Списано {result.redemption.points_spent} баллов один раз"
    )
    if target:
        await safe_send(
            bot,
            target.telegram_id,
            f"✅ Возможность «{result.reward.name}» подтверждена\n\n"
            f"Списано: {result.redemption.points_spent} баллов\n"
            f"Остаток: {balance} баллов\n\n"
            "Команда ЭРА свяжется с Вами по дальнейшим шагам",
        )


@router.callback_query(F.data == "admin:auctions")
async def auctions_admin_menu(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    auctions = (
        await session.scalars(
            select(Auction).order_by(Auction.created_at.desc()).limit(30)
        )
    ).all()
    rows = [
        [
            InlineKeyboardButton(
                text="➕ Новый аукцион", callback_data="admin:auction:new"
            )
        ]
    ]
    rows.extend(
        [
            InlineKeyboardButton(
                text=f"{item.title} · {item.status}",
                callback_data=f"admin:auction:view:{item.id}",
            )
        ]
        for item in auctions
    )
    rows.append(
        [InlineKeyboardButton(text="← Назад", callback_data="admin:menu:growth")]
    )
    await call.message.answer(
        "🔨 Аукционы возможностей\n\nСоздайте лот, выберите аудиторию и срок. Победителя Вы подтверждаете вручную",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "admin:auction:new")
async def auction_new_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminAuctionStates.audience)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Все участники", callback_data="admin:auction:audience:all"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Участники", callback_data="admin:auction:audience:participant"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Активисты", callback_data="admin:auction:audience:activist"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Лидеры", callback_data="admin:auction:audience:leader"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Руководители", callback_data="admin:auction:audience:head"
                )
            ],
        ]
    )
    await call.message.answer(
        "Кто сможет участвовать в аукционе?", reply_markup=keyboard
    )


@router.callback_query(
    AdminAuctionStates.audience, F.data.startswith("admin:auction:audience:")
)
async def auction_audience(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    audience = call.data.rsplit(":", 1)[-1]
    await state.update_data(auction_audience=audience)
    await state.set_state(AdminAuctionStates.title)
    await call.message.answer("Как называется возможность, которую разыгрываем?")


@router.message(AdminAuctionStates.title)
async def auction_title(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 255)
    if not value:
        return
    await state.update_data(auction_title=value)
    await state.set_state(AdminAuctionStates.description)
    await message.answer("Опишите, что получит победитель и важные условия")


@router.message(AdminAuctionStates.description)
async def auction_description(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 2000)
    if not value:
        return
    await state.update_data(auction_description=value)
    await state.set_state(AdminAuctionStates.minimum)
    await message.answer("Минимальная ставка в баллах")


@router.message(AdminAuctionStates.minimum)
async def auction_minimum(message: Message, state: FSMContext) -> None:
    try:
        value = int((message.text or "").strip())
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите положительное целое число")
        return
    await state.update_data(auction_minimum=value)
    await state.set_state(AdminAuctionStates.step)
    await message.answer("Минимальный шаг новой ставки")


@router.message(AdminAuctionStates.step)
async def auction_step(message: Message, state: FSMContext) -> None:
    try:
        value = int((message.text or "").strip())
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите положительное целое число")
        return
    await state.update_data(auction_step=value)
    await state.set_state(AdminAuctionStates.deadline)
    await message.answer("Когда завершить аукцион? Формат: ДД.ММ.ГГГГ ЧЧ:ММ")


@router.message(AdminAuctionStates.deadline)
async def auction_deadline(
    message: Message, state: FSMContext, settings: Settings
) -> None:
    try:
        value = datetime.strptime(message.text or "", "%d.%m.%Y %H:%M").replace(
            tzinfo=ZoneInfo(settings.timezone)
        )
        if value <= datetime.now(ZoneInfo(settings.timezone)):
            raise ValueError
    except ValueError:
        await message.answer("Укажите будущую дату в формате ДД.ММ.ГГГГ ЧЧ:ММ")
        return
    await state.update_data(auction_deadline=value)
    await state.set_state(AdminAuctionStates.winners)
    await message.answer("Сколько победителей можно выбрать?")


@router.message(AdminAuctionStates.winners)
async def auction_finish(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(message, user, settings):
        return
    try:
        winners = int((message.text or "").strip())
        if not 1 <= winners <= 100:
            raise ValueError
    except ValueError:
        await message.answer("Введите число от 1 до 100")
        return
    data = await state.get_data()
    audience = data["auction_audience"]
    auction = Auction(
        title=data["auction_title"],
        description=data["auction_description"],
        audience_filter_json={} if audience == "all" else {"role": audience},
        starts_at=datetime.now(ZoneInfo(settings.timezone)),
        ends_at=data["auction_deadline"],
        minimum_bid=data["auction_minimum"],
        bid_step=data["auction_step"],
        winner_count=winners,
        status="active",
        created_by=user.id if user else 1,
    )
    session.add(auction)
    await session.flush()
    recipients_query = select(User).where(
        User.application_status == ApplicationStatus.APPROVED,
        User.is_archived.is_(False),
    )
    if audience != "all":
        recipients_query = recipients_query.where(User.role == audience)
    recipients = (await session.scalars(recipients_query)).all()
    await state.clear()
    await message.answer(f"Аукцион «{auction.title}» открыт и отправлен аудитории")
    await broadcast(
        bot,
        (target.telegram_id for target in recipients),
        f"🔨 Новый аукцион ЭРА\n\n{auction.title}\n\n{auction.description}\n\n"
        f"Минимальная ставка: {auction.minimum_bid} баллов\n"
        f"Завершение: {auction.ends_at:%d.%m.%Y %H:%M}\n\n"
        "Откройте «Мой путь» → «Награды и аукционы», чтобы участвовать",
    )


@router.callback_query(F.data.startswith("admin:auction:view:"))
async def auction_results(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    auction = await session.get(Auction, int(call.data.rsplit(":", 1)[-1]))
    if auction is None:
        return
    can_select = datetime.now(ZoneInfo(settings.timezone)) >= auction.ends_at
    if can_select and auction.status == "active":
        auction.status = "ended"
    bids = (
        await session.scalars(
            select(AuctionBid)
            .where(AuctionBid.auction_id == auction.id, AuctionBid.status == "active")
            .order_by(AuctionBid.amount.desc())
        )
    ).all()
    if not bids:
        await call.message.answer(f"🔨 {auction.title}\n\nСтавок пока нет")
        return
    for position, bid in enumerate(bids, 1):
        target = await session.get(User, bid.user_id)
        keyboard = (
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Выбрать победителем",
                            callback_data=f"admin:auction:winner:{bid.id}",
                        )
                    ]
                ]
            )
            if can_select
            else None
        )
        await call.message.answer(
            f"#{position} · {target.first_name} {target.last_name or ''}\n"
            f"Ставка: {bid.amount} баллов"
            + (
                "\n\nВыбор победителя откроется после завершения"
                if not can_select
                else ""
            ),
            reply_markup=keyboard,
        )


@router.callback_query(F.data.startswith("admin:auction:winner:"))
async def auction_select_winner(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    bid = await session.get(AuctionBid, int(call.data.rsplit(":", 1)[-1]))
    if bid is None or bid.status != "active":
        await call.message.answer("Эта ставка уже обработана")
        return
    auction = await session.get(Auction, bid.auction_id)
    if datetime.now(ZoneInfo(settings.timezone)) < auction.ends_at:
        await call.message.answer(
            "Победителя можно выбрать только после завершения аукциона"
        )
        return
    selected = int(
        await session.scalar(
            select(func.count())
            .select_from(AuctionBid)
            .where(AuctionBid.auction_id == auction.id, AuctionBid.status == "won")
        )
        or 0
    )
    if selected >= auction.winner_count:
        await call.message.answer("Все места победителей уже распределены")
        return
    balance = await total_points(session, bid.user_id)
    if balance < bid.amount:
        bid.status = "insufficient_points"
        await call.message.answer("У участника уже недостаточно баллов — ставка снята")
        return
    await add_points(
        session,
        user_id=bid.user_id,
        points=-bid.amount,
        reason=f"Победа в аукционе: {auction.title}",
        approved_by=user.id if user else None,
    )
    bid.status = "won"
    bid.selected_by = user.id if user else None
    bid.selected_at = datetime.now().astimezone()
    target = await session.get(User, bid.user_id)
    await call.message.answer("Победитель подтверждён, баллы списаны")
    if target:
        await safe_send(
            bot,
            target.telegram_id,
            f"Вы стали победителем аукциона «{auction.title}» 🎉\n\n"
            f"Списано {bid.amount} баллов. Команда ЭРА свяжется с Вами по дальнейшим шагам",
        )


@router.message(Command("portfolio"))
async def portfolio_add_command(
    message: Message,
    command: CommandObject,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(message, user, settings):
        return
    try:
        telegram_id, item_type, title, description = [
            x.strip() for x in (command.args or "").split("|", 3)
        ]
        target = await session.scalar(
            select(User).where(User.telegram_id == int(telegram_id))
        )
        if target is None:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer(
            "Формат: /portfolio Telegram_ID | тип | название | описание"
        )
        return
    reply = message.reply_to_message
    file_id = None
    if reply:
        if reply.document:
            file_id = reply.document.file_id
        elif reply.photo:
            file_id = reply.photo[-1].file_id
    url = description if description.startswith(("https://", "http://")) else None
    await add_portfolio_item(
        session,
        user_id=target.id,
        title=title,
        item_type=item_type,
        description=description,
        issued_by=user.id if user else None,
        file_id=file_id,
        url=url,
    )
    await message.answer("Достижение добавлено в портфолио.")


@router.callback_query(F.data == "admin:points")
async def points_help(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.clear()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Начислить или списать баллы",
                    callback_data="admin:growth:start:points",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Вручить знак", callback_data="admin:growth:start:badge"
                )
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="admin:menu:growth")],
        ]
    )
    await call.message.answer(
        "⭐ Баллы и знаки\n\nВыберите действие — бот сам найдёт участника и проведёт по шагам",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.regexp(r"^admin:growth:start:(points|badge)$"))
async def growth_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    action = call.data.rsplit(":", 1)[-1]
    await state.set_state(AdminGrowthStates.person)
    await state.update_data(growth_action=action)
    await call.message.answer(
        "Напишите имя, фамилию, @username или Telegram ID участника"
    )


@router.message(AdminGrowthStates.person)
async def growth_find_person(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(message, user, settings):
        return
    query = clean_text(message.text or "", 150)
    if not query:
        return
    normalized = query.lstrip("@").lower()
    conditions = [
        func.lower(User.first_name).contains(normalized),
        func.lower(func.coalesce(User.last_name, "")).contains(normalized),
        func.lower(func.coalesce(User.username, "")).contains(normalized),
    ]
    if normalized.isdigit():
        conditions.append(User.telegram_id == int(normalized))
    matches = (
        await session.scalars(
            select(User)
            .where(or_(*conditions), User.is_archived.is_(False))
            .order_by(User.first_name)
            .limit(8)
        )
    ).all()
    if not matches:
        await message.answer(
            "Никого не нашёл — проверьте написание и попробуйте ещё раз"
        )
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{target.first_name} {target.last_name or ''}".strip(),
                    callback_data=f"admin:growth:person:{target.id}",
                )
            ]
            for target in matches
        ]
    )
    await message.answer("Выберите участника", reply_markup=keyboard)


@router.callback_query(
    AdminGrowthStates.person, F.data.startswith("admin:growth:person:")
)
async def growth_select_person(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    target_id = int(call.data.rsplit(":", 1)[-1])
    data = await state.get_data()
    await state.update_data(growth_target_id=target_id)
    if data.get("growth_action") == "points":
        await state.set_state(AdminGrowthStates.points)
        await call.message.answer(
            "Сколько баллов изменить?\n\nПоложительное число начислит баллы, отрицательное — спишет"
        )
        return
    badges = (await session.scalars(select(Badge).order_by(Badge.name))).all()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=badge.name,
                    callback_data=f"admin:growth:badge:{badge.id}",
                )
            ]
            for badge in badges
        ]
    )
    await call.message.answer("Какой знак вручить?", reply_markup=keyboard)


@router.message(AdminGrowthStates.points)
async def growth_points_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = int((message.text or "").strip())
        if amount == 0 or abs(amount) > 10000:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое число от -10000 до 10000, кроме нуля")
        return
    await state.update_data(growth_amount=amount)
    await state.set_state(AdminGrowthStates.reason)
    await message.answer("За что меняем баллы? Напишите короткую понятную причину")


@router.callback_query(
    AdminGrowthStates.person, F.data.startswith("admin:growth:badge:")
)
async def growth_badge_select(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(growth_badge_id=int(call.data.rsplit(":", 1)[-1]))
    await state.set_state(AdminGrowthStates.reason)
    await call.message.answer("Напишите, за что участник получает этот знак")


@router.message(AdminGrowthStates.reason)
async def growth_finish(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(message, user, settings):
        return
    reason = clean_text(message.text or "", 500)
    if not reason:
        return
    data = await state.get_data()
    target = await session.get(User, int(data["growth_target_id"]))
    if target is None:
        await state.clear()
        return
    if data.get("growth_action") == "points":
        amount = int(data["growth_amount"])
        await add_points(
            session,
            user_id=target.id,
            points=amount,
            reason=reason,
            approved_by=user.id if user else None,
        )
        notice = f"Ваш баланс изменён на {amount:+d} баллов\nПричина: {reason}"
    else:
        badge = await session.get(Badge, int(data["growth_badge_id"]))
        session.add(
            UserBadge(
                user_id=target.id,
                badge_id=badge.id,
                reason=reason,
                awarded_by=user.id if user else None,
            )
        )
        await add_portfolio_item(
            session,
            user_id=target.id,
            title=badge.name,
            item_type="badge",
            description=reason,
            issued_by=user.id if user else None,
        )
        notice = f"Вы получили знак «{badge.name}» 🌟\n\n{reason}"
    await state.clear()
    await message.answer("Готово — изменение сохранено, участник получил уведомление")
    await safe_send(bot, target.telegram_id, notice)


@router.message(Command("addpoints"))
async def addpoints_command(
    message: Message,
    command: CommandObject,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(message, user, settings):
        return
    try:
        telegram_id, amount, reason = (command.args or "").split(maxsplit=2)
        target = await session.scalar(
            select(User).where(User.telegram_id == int(telegram_id))
        )
        if target is None:
            raise ValueError
        amount_value = int(amount)
    except (ValueError, TypeError):
        await message.answer("Формат: /addpoints Telegram_ID количество причина")
        return
    await add_points(
        session,
        user_id=target.id,
        points=amount_value,
        reason=reason,
        approved_by=user.id if user else None,
    )
    await message.answer("Баллы начислены.")
    await safe_send(
        bot,
        target.telegram_id,
        f"Вам начислены баллы: {amount_value}. Причина: {reason}",
    )


@router.message(Command("awardbadge"))
async def award_badge(
    message: Message,
    command: CommandObject,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(message, user, settings):
        return
    try:
        raw_id, badge_name, reason = [
            x.strip() for x in (command.args or "").split("|", 2)
        ]
        target = await session.scalar(
            select(User).where(User.telegram_id == int(raw_id))
        )
        badge = await session.scalar(select(Badge).where(Badge.name == badge_name))
        if target is None or badge is None:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer(
            "Формат: /awardbadge Telegram_ID | название знака | причина"
        )
        return
    session.add(
        UserBadge(
            user_id=target.id, badge_id=badge.id, reason=reason, awarded_by=user.id
        )
    )
    await add_portfolio_item(
        session,
        user_id=target.id,
        title=badge.name,
        item_type="badge",
        description=reason,
        issued_by=user.id,
    )
    await add_points(
        session,
        user_id=target.id,
        points=20,
        reason="Получение знака отличия",
        approved_by=user.id,
    )
    await message.answer("Знак выдан.")
    await safe_send(
        bot,
        target.telegram_id,
        f"У Вас новый знак отличия.\n\n{badge.name}\n\nПричина: {reason}\n\nЭто признание Вашего вклада в ЭРА.",
    )


@router.callback_query(F.data == "admin:roles")
async def roles_help(
    call: CallbackQuery, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.answer(
        "Роли и статусы участников\n\nВыберите группу, затем откройте карточку человека — роль и статус меняются обычными кнопками",
        reply_markup=role_filters_keyboard(),
    )


async def _set_enum_value(
    message: Message,
    command: CommandObject,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    field: str,
    allowed: set[str],
) -> None:
    if not await _guard(message, user, settings):
        return
    try:
        raw_id, value = (command.args or "").split(maxsplit=1)
        if value not in allowed:
            raise ValueError
        target = await session.scalar(
            select(User).where(User.telegram_id == int(raw_id))
        )
        if target is None:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer(
            f"Проверьте Telegram ID и значение. Допустимо: {', '.join(sorted(allowed))}"
        )
        return
    old = getattr(target, field)
    setattr(target, field, value)
    await audit(
        session,
        actor_id=user.id if user else None,
        action=f"user.{field}_changed",
        entity_type="user",
        entity_id=target.id,
        old_value={field: old},
        new_value={field: value},
    )
    await message.answer("Изменение сохранено.")


@router.message(Command("setrole"))
async def set_role(
    message: Message,
    command: CommandObject,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    await _set_enum_value(
        message, command, user, settings, session, "role", {x.value for x in Role}
    )


@router.message(Command("setstatus"))
async def set_status(
    message: Message,
    command: CommandObject,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    await _set_enum_value(
        message,
        command,
        user,
        settings,
        session,
        "participation_status",
        {x.value for x in ParticipationStatus},
    )


@router.callback_query(F.data == "admin:participants")
async def participants(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.answer(
        "Участники ЭРА 👥\n\nНайдите человека по имени или Telegram либо выберите удобный фильтр",
        reply_markup=people_filters_keyboard(),
    )


@router.callback_query(F.data == "admin:people:roles")
async def people_roles(
    call: CallbackQuery, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.answer("Выберите роль", reply_markup=role_filters_keyboard())


@router.callback_query(F.data == "admin:people:ages")
async def people_ages(
    call: CallbackQuery, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.answer(
        "Выберите возрастную группу", reply_markup=age_filters_keyboard()
    )


@router.callback_query(F.data == "admin:people:cities")
async def people_cities(
    call: CallbackQuery,
    state: FSMContext,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    cities = list(
        await session.scalars(
            select(User.city)
            .where(
                User.application_status == ApplicationStatus.APPROVED,
                User.city.is_not(None),
                User.is_archived.is_(False),
            )
            .distinct()
            .order_by(User.city)
            .limit(30)
        )
    )
    await state.update_data(admin_city_values=cities)
    rows = [
        [
            InlineKeyboardButton(
                text=city, callback_data=f"admin:people:list:city:{index}:0"
            )
        ]
        for index, city in enumerate(cities)
    ]
    rows.append(
        [InlineKeyboardButton(text="← К фильтрам", callback_data="admin:participants")]
    )
    await call.message.answer(
        "Выберите город" if cities else "В анкетах пока нет городов",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "admin:people:directions")
async def people_directions(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    directions = (
        await session.scalars(select(Direction).order_by(Direction.name))
    ).all()
    rows = [
        [
            InlineKeyboardButton(
                text=direction.name,
                callback_data=f"admin:people:list:direction:{direction.id}:0",
            )
        ]
        for direction in directions
    ]
    rows.append(
        [InlineKeyboardButton(text="← К фильтрам", callback_data="admin:participants")]
    )
    await call.message.answer(
        "Выберите направление",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "admin:people:search")
async def people_search_start(
    call: CallbackQuery,
    state: FSMContext,
    user: User | None,
    settings: Settings,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminPeopleStates.search)
    await call.message.answer(
        "Напишите имя, фамилию, @username или Telegram ID\n\nМожно указать только часть имени"
    )


@router.message(AdminPeopleStates.search)
async def people_search_finish(
    message: Message,
    state: FSMContext,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(message, user, settings):
        return
    term = clean_text(message.text or "", 100)
    if not term:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(admin_people_search=term.lstrip("@"))
    await state.set_state(None)
    await _send_people_page(message, session, state, "search", "0", 0)


async def _send_people_page(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    kind: str,
    value: str,
    page: int,
) -> None:
    query = select(User).where(
        User.application_status == ApplicationStatus.APPROVED,
        User.is_archived.is_(False),
    )
    label = "Все участники"
    if kind == "role":
        query = query.where(User.role == value)
        label = f"Роль: {ROLE_LABELS.get(value, value)}"
    elif kind == "age":
        bounds = {
            "14_17": (14, 17),
            "18_24": (18, 24),
            "25_34": (25, 34),
            "35_plus": (35, 100),
        }
        low, high = bounds[value]
        query = query.where(User.age.between(low, high))
        label = f"Возраст: {low}–{high}"
    elif kind == "city":
        cities = (await state.get_data()).get("admin_city_values", [])
        try:
            city = cities[int(value)]
        except (IndexError, ValueError):
            await message.answer("Фильтр устарел — выберите город ещё раз")
            return
        query = query.where(User.city == city)
        label = f"Город: {city}"
    elif kind == "direction":
        query = query.join(UserDirection).where(
            UserDirection.direction_id == int(value)
        )
        direction = await session.get(Direction, int(value))
        label = f"Направление: {direction.name if direction else value}"
    elif kind == "search":
        term = (await state.get_data()).get("admin_people_search", "")
        pattern = f"%{term}%"
        conditions = [
            User.first_name.ilike(pattern),
            User.last_name.ilike(pattern),
            User.username.ilike(pattern),
        ]
        if term.isdigit():
            conditions.append(User.telegram_id == int(term))
        query = query.where(or_(*conditions))
        label = f"Поиск: {term}"
    per_page = 10
    rows = (
        (
            await session.scalars(
                query.order_by(User.first_name, User.last_name)
                .offset(page * per_page)
                .limit(per_page + 1)
            )
        )
        .unique()
        .all()
    )
    has_next = len(rows) > per_page
    rows = rows[:per_page]
    await message.answer(
        f"{label}\n\nНайдено на странице: {len(rows)}",
        reply_markup=people_list_keyboard(
            rows,
            kind=kind,
            value=value,
            page=page,
            has_next=has_next,
        ),
    )


@router.callback_query(F.data.startswith("admin:people:list:"))
async def people_list(
    call: CallbackQuery,
    state: FSMContext,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, _, kind, value, raw_page = call.data.split(":")
    await _send_people_page(call.message, session, state, kind, value, int(raw_page))


@router.callback_query(F.data.regexp(r"^admin:user:\d+$"))
async def admin_user_card(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    target = await session.get(User, int(call.data.rsplit(":", 1)[-1]))
    if target is None:
        await call.message.answer("Участник не найден")
        return
    departments = (
        ", ".join(item.department.name for item in target.departments) or "не выбраны"
    )
    directions = (
        ", ".join(item.direction.name for item in target.directions) or "не выбраны"
    )
    points = int(
        await session.scalar(
            select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                PointTransaction.user_id == target.id
            )
        )
        or 0
    )
    portfolio_count = int(
        await session.scalar(
            select(func.count())
            .select_from(PortfolioItem)
            .where(PortfolioItem.user_id == target.id)
        )
        or 0
    )
    telegram = f"@{target.username}" if target.username else str(target.telegram_id)
    body = f"""👤 {target.first_name} {target.last_name or ""}

Роль: {ROLE_LABELS.get(target.role, target.role)}
Статус: {STATUS_LABELS.get(target.participation_status, target.participation_status)}
Возраст: {target.age or "не указан"}
Город: {target.city or "не указан"}
Telegram: {telegram}
Email: {target.email or "не указан"}

Департаменты: {departments}
Направления: {directions}

Баланс: {points} баллов
Достижений в портфолио: {portfolio_count}

Мотивация
{target.motivation or "не указана"}"""
    await send_long_text(call.message, body, reply_markup=admin_user_actions(target.id))


@router.callback_query(F.data.regexp(r"^admin:user:role:\d+$"))
async def admin_user_role_menu(
    call: CallbackQuery, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user, settings):
        return
    target_id = int(call.data.rsplit(":", 1)[-1])
    await call.message.answer(
        "Выберите новую роль", reply_markup=user_role_keyboard(target_id)
    )


@router.callback_query(F.data.regexp(r"^admin:user:status:\d+$"))
async def admin_user_status_menu(
    call: CallbackQuery, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user, settings):
        return
    target_id = int(call.data.rsplit(":", 1)[-1])
    await call.message.answer(
        "Выберите новый статус участия",
        reply_markup=user_status_keyboard(target_id),
    )


@router.callback_query(F.data.startswith("admin:user:setrole:"))
async def admin_user_set_role(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, _, raw_id, value = call.data.split(":")
    target = await session.get(User, int(raw_id))
    if target is None or value not in {item.value for item in Role} - {Role.ADMIN}:
        await call.message.answer("Не удалось изменить роль")
        return
    old = target.role
    target.role = value
    await audit(
        session,
        actor_id=user.id if user else None,
        action="user.role_changed",
        entity_type="user",
        entity_id=target.id,
        old_value={"role": old},
        new_value={"role": value},
    )
    await call.message.answer(f"Роль изменена: {ROLE_LABELS.get(value, value)}")
    await safe_send(
        bot,
        target.telegram_id,
        f"Ваша роль в ЭРА изменена: {ROLE_LABELS.get(value, value)}\n\nНовые возможности уже доступны в обновлённом меню.",
        main_menu(
            settings.era_channel_url,
            privileged=value in {Role.LEADER, Role.HEAD, Role.COUNCIL, Role.ADMIN},
            admin=value == Role.ADMIN,
        ),
    )


@router.callback_query(F.data.startswith("admin:user:setstatus:"))
async def admin_user_set_status(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, _, raw_id, value = call.data.split(":")
    target = await session.get(User, int(raw_id))
    if target is None or value not in {item.value for item in ParticipationStatus}:
        await call.message.answer("Не удалось изменить статус")
        return
    old = target.participation_status
    target.participation_status = value
    await audit(
        session,
        actor_id=user.id if user else None,
        action="user.status_changed",
        entity_type="user",
        entity_id=target.id,
        old_value={"status": old},
        new_value={"status": value},
    )
    await call.message.answer(f"Статус изменён: {STATUS_LABELS.get(value, value)}")


@router.callback_query(F.data.regexp(r"^admin:user:portfolio:\d+$"))
async def admin_user_portfolio(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    target_id = int(call.data.rsplit(":", 1)[-1])
    items = (
        await session.scalars(
            select(PortfolioItem)
            .where(PortfolioItem.user_id == target_id)
            .order_by(PortfolioItem.created_at.desc())
            .limit(50)
        )
    ).all()
    body = (
        "\n\n".join(
            f"{item.title}\n{item.description or item.item_type}" for item in items
        )
        or "В портфолио пока нет подтверждённых достижений"
    )
    await send_long_text(
        call.message,
        body,
        reply_markup=admin_user_actions(target_id),
    )


@router.callback_query(F.data.regexp(r"^admin:user:archive:\d+$"))
async def admin_user_archive_start(
    call: CallbackQuery, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user, settings):
        return
    target_id = int(call.data.rsplit(":", 1)[-1])
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, удалить доступ",
                    callback_data=f"admin:user:archive_confirm:{target_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отмена", callback_data=f"admin:user:{target_id}"
                )
            ],
        ]
    )
    await call.message.answer(
        "Участник потеряет доступ к боту, но проекты, баллы и история останутся в архиве\n\nПродолжить?",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("admin:user:archive_confirm:"))
async def admin_user_archive_confirm(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    target = await session.get(User, int(call.data.rsplit(":", 1)[-1]))
    if target is None:
        return
    if user and target.id == user.id:
        await call.message.answer("Нельзя удалить собственный доступ")
        return
    target.is_archived = True
    target.archived_at = datetime.now().astimezone()
    target.archived_by = user.id if user else None
    await audit(
        session,
        actor_id=user.id if user else None,
        action="user.archived",
        entity_type="user",
        entity_id=target.id,
    )
    await call.message.answer("Участник перемещён в архив")


@router.callback_query(F.data == "admin:analytics")
async def analytics(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return

    async def count(model, *conditions) -> int:
        return int(
            await session.scalar(
                select(func.count()).select_from(model).where(*conditions)
            )
            or 0
        )

    body = (
        "Аналитика ЭРА\n\n"
        f"Участников: {await count(User, User.application_status == ApplicationStatus.APPROVED)}\n"
        f"Заявок: {await count(User, User.application_status == ApplicationStatus.PENDING)}\n"
        f"Мероприятий: {await count(Event)}\n"
        f"Проектов: {await count(Project)}\n"
        f"Вопросов без ответа: {await count(UserQuestion, UserQuestion.status == 'new')}\n"
        f"Материалов портфолио на проверке: {await count(PortfolioItem, PortfolioItem.status == 'pending')}"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Скачать Excel", callback_data="admin:analytics:excel"
                )
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="admin:menu:system")],
        ]
    )
    await call.message.answer(body, reply_markup=keyboard)


@router.callback_query(F.data == "admin:analytics:excel")
async def analytics_excel(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    users = (
        await session.scalars(
            select(User)
            .where(User.application_status == ApplicationStatus.APPROVED)
            .order_by(User.first_name)
        )
    ).all()
    events = (await session.scalars(select(Event).order_by(Event.event_date))).all()
    projects = (
        await session.scalars(select(Project).order_by(Project.created_at))
    ).all()
    totals = dict(
        (
            await session.execute(
                select(
                    PointTransaction.user_id,
                    func.coalesce(func.sum(PointTransaction.points), 0),
                ).group_by(PointTransaction.user_id)
            )
        ).all()
    )
    content = build_analytics_workbook(users, events, projects, totals)
    await call.message.answer_document(
        BufferedInputFile(content, filename="ERA_analytics.xlsx"),
        caption="Аналитика ЭРА: участники, мероприятия и проекты",
    )


@router.callback_query(F.data == "admin:offices")
async def offices_menu(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    offices = (
        await session.scalars(
            select(Office).where(Office.is_active.is_(True)).order_by(Office.sort_order)
        )
    ).all()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=office.title, callback_data=f"admin:office:view:{office.id}"
                )
            ]
            for office in offices
        ]
        + [
            [
                InlineKeyboardButton(
                    text="➕ Добавить должность", callback_data="admin:office:new"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔐 Делегировать права", callback_data="admin:permissions"
                )
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="admin:menu:system")],
        ]
    )
    await call.message.answer(
        "👥 Должности и ответственность\n\n"
        "Выберите должность, чтобы назначить человека или завершить полномочия",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("admin:office:view:"))
async def office_view(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    office = await session.get(Office, int(call.data.rsplit(":", 1)[-1]))
    if office is None:
        return
    assignments = (
        await session.scalars(
            select(UserOffice).where(
                UserOffice.office_id == office.id, UserOffice.is_active.is_(True)
            )
        )
    ).all()
    rows = [
        [
            InlineKeyboardButton(
                text="Назначить человека",
                callback_data=f"admin:office:assign:{office.id}",
            )
        ]
    ]
    names = []
    for assignment in assignments:
        target = await session.get(User, assignment.user_id)
        if target:
            names.append(f"{target.first_name} {target.last_name or ''}".strip())
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"Завершить: {target.first_name} {target.last_name or ''}".strip(),
                        callback_data=f"admin:office:remove:{assignment.id}",
                    )
                ]
            )
    rows.extend([\n        [\n            InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"admin:office:edit:{office.id}:title"),\n            InlineKeyboardButton(text="📝 Изменить описание", callback_data=f"admin:office:edit:{office.id}:description"),\n        ],\n        [InlineKeyboardButton(text="🗑 Удалить должность", callback_data=f"admin:office:disable:{office.id}")],\n        [InlineKeyboardButton(text="← Назад", callback_data="admin:offices")],\n    ])\n    await call.message.answer(\n        f"{office.title}\n\n{office.description or 'Описание можно добавить позже'}\n\n"
        f"Сейчас: {', '.join(names) or 'никто не назначен'}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("admin:office:assign:"))
async def office_assign_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminOfficeStates.person)
    await state.update_data(office_id=int(call.data.rsplit(":", 1)[-1]))
    await call.message.answer("Напишите имя, фамилию, @username или Telegram ID")


@router.message(AdminOfficeStates.person)
async def office_assign_find(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    query = clean_text(message.text or "", 150).lstrip("@").lower()
    conditions = [
        User.first_name.ilike(f"%{query}%"),
        User.last_name.ilike(f"%{query}%"),
        User.username.ilike(f"%{query}%"),
    ]
    if query.isdigit():
        conditions.append(User.telegram_id == int(query))
    targets = (
        await session.scalars(select(User).where(or_(*conditions)).limit(8))
    ).all()
    if not targets:
        await message.answer("Участник не найден")
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{target.first_name} {target.last_name or ''}".strip(),
                    callback_data=f"admin:office:person:{target.id}",
                )
            ]
            for target in targets
        ]
    )
    await message.answer("Кого назначить?", reply_markup=keyboard)


@router.callback_query(
    AdminOfficeStates.person, F.data.startswith("admin:office:person:")
)
async def office_assign_finish(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    office_id = int((await state.get_data())["office_id"])
    target_id = int(call.data.rsplit(":", 1)[-1])
    existing = await session.scalar(
        select(UserOffice).where(
            UserOffice.office_id == office_id,
            UserOffice.user_id == target_id,
            UserOffice.is_active.is_(True),
        )
    )
    if existing is None:
        session.add(
            UserOffice(
                office_id=office_id,
                user_id=target_id,
                appointed_by=user.id if user else target_id,
            )
        )
    await state.clear()
    await call.message.answer("Назначение сохранено и появится в контактах команды ЭРА")


@router.callback_query(F.data.startswith("admin:office:remove:"))
async def office_remove(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    assignment = await session.get(UserOffice, int(call.data.rsplit(":", 1)[-1]))
    if assignment:
        assignment.is_active = False
        assignment.ends_at = datetime.now().date()
    await call.message.answer("Полномочия завершены, история назначения сохранена")


@router.callback_query(F.data == "admin:office:new")
async def office_new_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminOfficeStates.title)
    await call.message.answer("Напишите название новой должности")


@router.message(AdminOfficeStates.title)
async def office_new_title(message: Message, state: FSMContext) -> None:
    title = clean_text(message.text or "", 150)
    if not title:
        return
    await state.update_data(office_title=title)
    await state.set_state(AdminOfficeStates.description)
    await message.answer("Коротко опишите ответственность этой должности")


@router.message(AdminOfficeStates.description)
async def office_new_finish(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(message, user, settings):
        return
    description = clean_text(message.text or "", 1000)
    data = await state.get_data()
    session.add(Office(title=data["office_title"], description=description))
    await state.clear()
    await message.answer("Новая должность добавлена")


@router.callback_query(F.data == "admin:permissions")
async def permissions_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminPermissionStates.person)
    await call.message.answer(
        "Кому делегировать права? Напишите имя, фамилию, @username или Telegram ID"
    )


@router.message(AdminPermissionStates.person)
async def permissions_find(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    query = clean_text(message.text or "", 150).lstrip("@").lower()
    conditions = [
        User.first_name.ilike(f"%{query}%"),
        User.last_name.ilike(f"%{query}%"),
        User.username.ilike(f"%{query}%"),
    ]
    if query.isdigit():
        conditions.append(User.telegram_id == int(query))
    targets = (
        await session.scalars(select(User).where(or_(*conditions)).limit(8))
    ).all()
    if not targets:
        await message.answer("Участник не найден")
        return
    await message.answer(
        "Выберите человека",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"{target.first_name} {target.last_name or ''}".strip(),
                        callback_data=f"admin:permissions:user:{target.id}",
                    )
                ]
                for target in targets
            ]
        ),
    )


@router.callback_query(
    AdminPermissionStates.person, F.data.startswith("admin:permissions:user:")
)
async def permissions_user(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    target_id = int(call.data.rsplit(":", 1)[-1])
    await state.clear()
    grants = (
        await session.scalars(
            select(PermissionGrant).where(PermissionGrant.user_id == target_id)
        )
    ).all()
    active = {grant.permission for grant in grants if grant.is_active}
    labels = {
        "people.view": "Смотреть участников",
        "people.manage": "Управлять участниками и должностями",
        "applications.review": "Рассматривать заявки",
        "projects.review": "Рассматривать проекты",
        "events.manage": "Управлять мероприятиями",
        "tasks.manage": "Управлять заданиями",
        "points.award": "Баллы, награды и аукционы",
        "portfolio.review": "Портфолио и сертификаты",
        "broadcasts.create": "Вопросы, рассылки и приветствия",
        "analytics.view": "Смотреть аналитику",
    }
    await call.message.answer(
        "Нажимайте на права, чтобы включать или отключать их",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"{'✅' if permission in active else '▫️'} {labels[permission]}",
                        callback_data=f"admin:permission:toggle:{target_id}:{permission}",
                    )
                ]
                for permission in PERMISSIONS
            ]
            + [[InlineKeyboardButton(text="← Назад", callback_data="admin:offices")]]
        ),
    )


@router.callback_query(F.data.startswith("admin:permission:toggle:"))
async def permission_toggle(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, _, raw_target, permission = call.data.split(":", 4)
    if permission not in PERMISSIONS:
        return
    target_id = int(raw_target)
    grant = await session.scalar(
        select(PermissionGrant).where(
            PermissionGrant.user_id == target_id,
            PermissionGrant.permission == permission,
            PermissionGrant.scope_type == "global",
            PermissionGrant.scope_id == 0,
        )
    )
    if grant:
        grant.is_active = not grant.is_active
        enabled = grant.is_active
    else:
        session.add(
            PermissionGrant(
                user_id=target_id,
                permission=permission,
                scope_type="global",
                scope_id=0,
                granted_by=user.id if user else target_id,
            )
        )
        enabled = True
    await call.message.answer("Право включено" if enabled else "Право отключено")


@router.callback_query(F.data == "admin:reports")
async def reports(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    items = (
        await session.scalars(
            select(Report).order_by(Report.created_at.desc()).limit(30)
        )
    ).all()
    body = (
        "\n".join(
            f"• #{x.id} {REPORT_TYPE_LABELS.get(x.report_type, 'Отчёт')} — "
            f"{REPORT_STATUS_LABELS.get(x.status, 'Статус уточняется')}"
            for x in items
        )
        or "Отчётов пока нет."
    )
    await call.message.answer(body)


@router.callback_query(F.data == "admin:broadcast")
async def broadcast_start(
    call: CallbackQuery, state: FSMContext, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.clear()
    await state.set_state(AdminBroadcastStates.audience)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Все участники", callback_data="broadcast:audience:all"
                )
            ],
            [
                InlineKeyboardButton(
                    text="По роли", callback_data="broadcast:audience:role"
                )
            ],
            [
                InlineKeyboardButton(
                    text="По департаменту",
                    callback_data="broadcast:audience:department",
                )
            ],
            [
                InlineKeyboardButton(
                    text="По направлению", callback_data="broadcast:audience:direction"
                )
            ],
            [
                InlineKeyboardButton(
                    text="По возрасту", callback_data="broadcast:audience:age"
                ),
                InlineKeyboardButton(
                    text="По городу", callback_data="broadcast:audience:city"
                ),
            ],
        ]
    )
    await call.message.answer("Выберите аудиторию рассылки.", reply_markup=keyboard)


@router.callback_query(F.data == "admin:greetings")
async def greetings_menu(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    greetings = (
        await session.scalars(select(ChatGreeting).order_by(ChatGreeting.id))
    ).all()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{'🟢' if item.is_enabled else '⚪'} {item.title}",
                    callback_data=f"admin:greeting:view:{item.id}",
                )
            ]
            for item in greetings
        ]
        + [
            [
                InlineKeyboardButton(
                    text="← Назад", callback_data="admin:menu:communications"
                )
            ]
        ]
    )
    await call.message.answer(
        "👋 Автоматические приветствия\n\nВыберите чат — текст можно менять, а приветствие включать и отключать отдельно",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("admin:greeting:view:"))
async def greeting_view(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    item = await session.get(ChatGreeting, int(call.data.rsplit(":", 1)[-1]))
    if item is None:
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Изменить текст",
                    callback_data=f"admin:greeting:edit:{item.id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отключить" if item.is_enabled else "Включить",
                    callback_data=f"admin:greeting:toggle:{item.id}",
                )
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="admin:greetings")],
        ]
    )
    await call.message.answer(
        f"{item.title}\n\nСтатус: {'включено' if item.is_enabled else 'выключено'}\n\n"
        f"Текст приветствия:\n{item.text}\n\n"
        "Можно использовать {name} — бот подставит имя нового участника",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("admin:greeting:toggle:"))
async def greeting_toggle(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    item = await session.get(ChatGreeting, int(call.data.rsplit(":", 1)[-1]))
    if item is None:
        return
    item.is_enabled = not item.is_enabled
    item.updated_by = user.id if user else None
    await call.message.answer(
        f"Приветствие для чата «{item.title}» {'включено' if item.is_enabled else 'отключено'}"
    )


@router.callback_query(F.data.startswith("admin:greeting:edit:"))
async def greeting_edit_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminGrowthStates.greeting)
    await state.update_data(greeting_id=int(call.data.rsplit(":", 1)[-1]))
    await call.message.answer(
        "Напишите новый текст приветствия\n\nИспользуйте {name}, если хотите обратиться по имени"
    )


@router.message(AdminGrowthStates.greeting)
async def greeting_edit_finish(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(message, user, settings):
        return
    text = clean_text(message.text or "", 3000)
    if not text:
        return
    item = await session.get(ChatGreeting, int((await state.get_data())["greeting_id"]))
    if item:
        item.text = text
        item.updated_by = user.id if user else None
    await state.clear()
    await message.answer("Приветствие обновлено и уже будет использоваться в чате")


@router.callback_query(
    AdminBroadcastStates.audience, F.data.startswith("broadcast:audience:")
)
async def broadcast_audience(
    call: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await call.answer()
    audience = call.data.rsplit(":", 1)[-1]
    await state.update_data(broadcast_audience=audience)
    if audience == "all":
        await state.set_state(AdminBroadcastStates.text)
        await call.message.answer("Напишите текст рассылки.")
        return
    await state.set_state(AdminBroadcastStates.filter_value)
    options = []
    if audience == "role":
        options = [
            ("Участники", "participant"),
            ("Активисты", "activist"),
            ("Лидеры", "leader"),
            ("Руководители", "head"),
            ("Совет", "council"),
        ]
    elif audience == "age":
        options = [
            ("14–17", "14_17"),
            ("18–24", "18_24"),
            ("25–34", "25_34"),
            ("35+", "35_plus"),
        ]
    elif audience == "department":
        options = [
            (item.name, f"id_{item.id}")
            for item in (
                await session.scalars(select(Department).order_by(Department.name))
            ).all()
        ]
    elif audience == "direction":
        options = [
            (item.name, f"id_{item.id}")
            for item in (
                await session.scalars(select(Direction).order_by(Direction.name))
            ).all()
        ]
    if options:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=label, callback_data=f"broadcast:filter:{value}"
                    )
                ]
                for label, value in options
            ]
        )
        await call.message.answer("Выберите значение фильтра", reply_markup=keyboard)
    else:
        await call.message.answer("Напишите город так, как он указан в анкетах")


@router.callback_query(
    AdminBroadcastStates.filter_value, F.data.startswith("broadcast:filter:")
)
async def broadcast_filter_button(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(broadcast_filter=call.data.split(":", 2)[-1])
    await state.set_state(AdminBroadcastStates.text)
    await call.message.answer("Напишите текст рассылки")


@router.message(AdminBroadcastStates.filter_value)
async def broadcast_filter(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 100)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(broadcast_filter=value)
    await state.set_state(AdminBroadcastStates.text)
    await message.answer("Напишите текст рассылки.")


@router.message(AdminBroadcastStates.text)
async def broadcast_text(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 3500)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(broadcast_text=value)
    await state.set_state(AdminBroadcastStates.confirm)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отправить", callback_data="broadcast:confirm:yes"
                )
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="broadcast:confirm:no")],
        ]
    )
    await message.answer(f"Проверьте рассылку:\n\n{value}", reply_markup=keyboard)


@router.callback_query(
    AdminBroadcastStates.confirm, F.data.startswith("broadcast:confirm:")
)
async def broadcast_finish(
    call: CallbackQuery,
    state: FSMContext,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    if call.data.endswith(":no"):
        await state.clear()
        await call.message.answer(texts.ACTION_CANCELLED)
        return
    data = await state.get_data()
    audience = data["broadcast_audience"]
    query = select(User).where(
        User.application_status == ApplicationStatus.APPROVED,
        User.is_blocked.is_(False),
    )
    filter_value = data.get("broadcast_filter")
    if audience == "role":
        query = query.where(User.role == filter_value)
    elif audience == "department":
        query = query.join(UserDepartment).where(
            UserDepartment.department_id == int(filter_value.removeprefix("id_"))
        )
    elif audience == "direction":
        query = query.join(UserDirection).where(
            UserDirection.direction_id == int(filter_value.removeprefix("id_"))
        )
    elif audience == "city":
        query = query.where(func.lower(User.city) == filter_value.lower())
    elif audience == "age":
        ranges = {
            "14_17": (14, 17),
            "18_24": (18, 24),
            "25_34": (25, 34),
            "35_plus": (35, 200),
        }
        low, high = ranges[filter_value]
        query = query.where(User.age.between(low, high))
    recipients = (await session.scalars(query)).unique().all()
    item = Broadcast(
        title="Рассылка ЭРА",
        text=data["broadcast_text"],
        audience_type=audience,
        audience_filter_json={"value": filter_value} if filter_value else {},
        author_id=user.id,
        status="sending",
    )
    session.add(item)
    await session.flush()
    sent, failed = await broadcast(bot, (x.telegram_id for x in recipients), item.text)
    item.status = "sent"
    item.sent_at = datetime.now().astimezone()
    await audit(
        session,
        actor_id=user.id,
        action="broadcast.sent",
        entity_type="broadcast",
        entity_id=item.id,
        new_value={"sent": sent, "failed": failed},
    )
    await state.clear()
    await call.message.answer(
        f"Рассылка завершена. Доставлено: {sent}. Ошибок: {failed}."
    )


@router.callback_query(F.data == "admin:departments")
async def department_applications(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    items = (
        await session.scalars(
            select(DepartmentApplication)
            .where(DepartmentApplication.status == "pending")
            .order_by(DepartmentApplication.created_at)
        )
    ).all()
    if not items:
        await call.message.answer("Заявок в департаменты на рассмотрении нет.")
        return
    for item in items:
        target = await session.get(User, item.user_id)
        department = await session.get(Department, item.department_id)
        direction = (
            await session.get(Direction, item.direction_id)
            if item.direction_id
            else None
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Одобрить",
                        callback_data=f"admin:deptapp:approve:{item.id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Отклонить",
                        callback_data=f"admin:deptapp:reject:{item.id}",
                    )
                ],
            ]
        )
        await call.message.answer(
            f"Заявка в департамент #{item.id}\n\n"
            f"Участник: {target.first_name if target else item.user_id}\n"
            f"Департамент: {department.name if department else item.department_id}\n"
            f"Направление: {direction.name if direction else 'не указано'}\n"
            f"Мотивация: {item.motivation}\nПольза: {item.usefulness}\n"
            f"Время: {item.available_time}",
            reply_markup=keyboard,
        )


@router.callback_query(F.data.regexp(r"^admin:deptapp:(approve|reject):\d+$"))
async def decide_department_application(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, action, raw_id = call.data.split(":")
    item = await session.get(DepartmentApplication, int(raw_id))
    if item is None or item.status != "pending":
        return
    item.status = "approved" if action == "approve" else "rejected"
    target = await session.get(User, item.user_id)
    if action == "approve" and target:
        exists_department = await session.scalar(
            select(UserDepartment).where(
                UserDepartment.user_id == target.id,
                UserDepartment.department_id == item.department_id,
            )
        )
        if exists_department:
            exists_department.status = "member"
        else:
            session.add(
                UserDepartment(
                    user_id=target.id, department_id=item.department_id, status="member"
                )
            )
        if item.direction_id:
            exists_direction = await session.scalar(
                select(UserDirection).where(
                    UserDirection.user_id == target.id,
                    UserDirection.direction_id == item.direction_id,
                )
            )
            if exists_direction:
                exists_direction.status = "member"
            else:
                session.add(
                    UserDirection(
                        user_id=target.id,
                        direction_id=item.direction_id,
                        status="member",
                    )
                )
    await audit(
        session,
        actor_id=user.id if user else None,
        action=f"department_application.{action}",
        entity_type="department_application",
        entity_id=item.id,
    )
    await call.message.answer("Решение по заявке сохранено.")
    if target:
        notice = (
            "Ваша заявка в департамент одобрена. Добро пожаловать в команду."
            if action == "approve"
            else "Сейчас заявка в департамент не одобрена. Вы можете задать вопрос команде ЭРА."
        )
        await safe_send(bot, target.telegram_id, notice)


@router.callback_query(F.data == "admin:tasks")
async def tasks_for_review(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.answer(
        "✅ Задания и конкурсы",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="➕ Создать задание или конкурс",
                        callback_data="admin:task:new",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="← Назад", callback_data="admin:menu:activity"
                    )
                ],
            ]
        ),
    )
    submissions = (
        await session.scalars(
            select(TaskSubmission)
            .where(TaskSubmission.status == "pending")
            .order_by(TaskSubmission.created_at)
        )
    ).all()
    if not submissions:
        await call.message.answer(
            "✅ Задания и конкурсы\n\nНовых результатов на проверке нет"
        )
        return
    for submission in submissions:
        task = await session.get(Task, submission.task_id)
        target = await session.get(User, submission.user_id)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"Принять · +{task.points}",
                        callback_data=f"admin:task_submission:approve:{submission.id}",
                    ),
                    InlineKeyboardButton(
                        text="Вернуть",
                        callback_data=f"admin:task_submission:revise:{submission.id}",
                    ),
                ],
            ]
        )
        await call.message.answer(
            f"✅ Результат задания\n\n{task.title}\n\n"
            f"Участник: {target.first_name if target else submission.user_id} "
            f"{target.last_name or '' if target else ''}\n"
            f"Награда: {task.points} баллов\n\n"
            f"{submission.text or 'Результат прикреплён файлом'}",
            reply_markup=keyboard,
        )


@router.callback_query(F.data == "admin:task:new")
async def admin_task_new(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminTaskStates.mode)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Личное задание", callback_data="admin:task:mode:private"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Открытое задание", callback_data="admin:task:mode:open"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Конкурс", callback_data="admin:task:mode:challenge"
                )
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="admin:tasks")],
        ]
    )
    await call.message.answer("Какой формат нужен?", reply_markup=keyboard)


@router.callback_query(AdminTaskStates.mode, F.data.startswith("admin:task:mode:"))
async def admin_task_mode(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    mode = call.data.rsplit(":", 1)[-1]
    await state.update_data(admin_task_mode=mode)
    if mode == "private":
        await state.set_state(AdminTaskStates.person)
        await call.message.answer(
            "Напишите имя, фамилию, @username или Telegram ID исполнителя"
        )
        return
    await state.set_state(AdminTaskStates.audience)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Все участники", callback_data="admin:task:audience:all"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Участники", callback_data="admin:task:audience:participant"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Активисты", callback_data="admin:task:audience:activist"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Лидеры", callback_data="admin:task:audience:leader"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Руководители", callback_data="admin:task:audience:head"
                )
            ],
        ]
    )
    await call.message.answer("Кому показать задание?", reply_markup=keyboard)


@router.message(AdminTaskStates.person)
async def admin_task_person_find(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    query = clean_text(message.text or "", 150).lstrip("@").lower()
    conditions = [
        User.first_name.ilike(f"%{query}%"),
        User.last_name.ilike(f"%{query}%"),
        User.username.ilike(f"%{query}%"),
    ]
    if query.isdigit():
        conditions.append(User.telegram_id == int(query))
    targets = (
        await session.scalars(select(User).where(or_(*conditions)).limit(8))
    ).all()
    if not targets:
        await message.answer("Исполнитель не найден")
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{target.first_name} {target.last_name or ''}".strip(),
                    callback_data=f"admin:task:person:{target.id}",
                )
            ]
            for target in targets
        ]
    )
    await message.answer("Выберите исполнителя", reply_markup=keyboard)


@router.callback_query(AdminTaskStates.person, F.data.startswith("admin:task:person:"))
async def admin_task_person(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(admin_task_assignee=int(call.data.rsplit(":", 1)[-1]))
    await state.set_state(AdminTaskStates.title)
    await call.message.answer("Название задания")


@router.callback_query(
    AdminTaskStates.audience, F.data.startswith("admin:task:audience:")
)
async def admin_task_audience(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(admin_task_audience=call.data.rsplit(":", 1)[-1])
    await state.set_state(AdminTaskStates.title)
    await call.message.answer("Название задания или конкурса")


@router.message(AdminTaskStates.title)
async def admin_task_title(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 255)
    if not value:
        return
    await state.update_data(admin_task_title=value)
    await state.set_state(AdminTaskStates.description)
    await message.answer("Опишите ТЗ и ожидаемый результат")


@router.message(AdminTaskStates.description)
async def admin_task_description(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 3000)
    if not value:
        return
    await state.update_data(admin_task_description=value)
    await state.set_state(AdminTaskStates.deadline)
    await message.answer("Дедлайн: ДД.ММ.ГГГГ ЧЧ:ММ")


@router.message(AdminTaskStates.deadline)
async def admin_task_deadline(
    message: Message, state: FSMContext, settings: Settings
) -> None:
    try:
        value = datetime.strptime(message.text or "", "%d.%m.%Y %H:%M").replace(
            tzinfo=ZoneInfo(settings.timezone)
        )
    except ValueError:
        await message.answer("Проверьте формат: ДД.ММ.ГГГГ ЧЧ:ММ")
        return
    await state.update_data(admin_task_deadline=value)
    await state.set_state(AdminTaskStates.points)
    await message.answer("Сколько баллов получит участник после проверки?")


@router.message(AdminTaskStates.points)
async def admin_task_points(message: Message, state: FSMContext) -> None:
    try:
        value = int((message.text or "").strip())
        if not 0 <= value <= 1000:
            raise ValueError
    except ValueError:
        await message.answer("Введите число от 0 до 1000")
        return
    await state.update_data(admin_task_points=value)
    data = await state.get_data()
    if data["admin_task_mode"] == "private":
        await state.update_data(admin_task_max=1)
        await state.set_state(AdminTaskStates.chat_url)
        await message.answer("Пришлите ссылку на рабочий чат или напишите «нет»")
        return
    await state.set_state(AdminTaskStates.max_participants)
    await message.answer("Максимум исполнителей? Отправьте 0, если без ограничения")


@router.message(AdminTaskStates.max_participants)
async def admin_task_max(message: Message, state: FSMContext) -> None:
    try:
        value = int((message.text or "").strip())
        if value < 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите 0 или положительное число")
        return
    await state.update_data(admin_task_max=value or None)
    await state.set_state(AdminTaskStates.chat_url)
    await message.answer("Пришлите ссылку на чат команды или напишите «нет»")


@router.message(AdminTaskStates.chat_url)
async def admin_task_finish(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(message, user, settings):
        return
    raw_url = (message.text or "").strip()
    chat_url = raw_url if raw_url.startswith(("https://", "http://")) else None
    data = await state.get_data()
    mode = data["admin_task_mode"]
    audience = data.get("admin_task_audience", "all")
    task = Task(
        title=data["admin_task_title"],
        description=data["admin_task_description"],
        assignee_id=data.get("admin_task_assignee"),
        creator_id=user.id if user else 1,
        deadline=data["admin_task_deadline"],
        points=data["admin_task_points"],
        task_type=mode,
        audience_filter_json={} if audience == "all" else {"role": audience},
        chat_url=chat_url,
        max_participants=data.get("admin_task_max"),
        status="new" if mode == "private" else "published",
        remind_at=datetime.now(ZoneInfo(settings.timezone)) + timedelta(days=1),
    )
    session.add(task)
    await session.flush()
    if mode == "private":
        recipients = [await session.get(User, task.assignee_id)]
    else:
        query = select(User).where(
            User.application_status == ApplicationStatus.APPROVED,
            User.is_archived.is_(False),
        )
        if audience != "all":
            query = query.where(User.role == audience)
        recipients = (await session.scalars(query)).all()
    await state.clear()
    await message.answer("Задание опубликовано, участники получили уведомление")
    for target in recipients:
        if target:
            await safe_send(
                bot,
                target.telegram_id,
                f"✅ Новое задание ЭРА\n\n{task.title}\n{task.description}\n\n"
                f"Дедлайн: {task.deadline:%d.%m.%Y %H:%M}\n"
                f"Награда: {task.points} баллов\n\n"
                "Откройте «Мой путь» → «Мои задания»",
            )


@router.callback_query(F.data.regexp(r"^admin:task_submission:(approve|revise):\d+$"))
async def decide_task_submission(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, action, raw_id = call.data.split(":")
    submission = await session.get(TaskSubmission, int(raw_id))
    if submission is None or submission.status != "pending":
        await call.message.answer("Результат уже проверен")
        return
    task = await session.get(Task, submission.task_id)
    target = await session.get(User, submission.user_id)
    submission.status = "approved" if action == "approve" else "revision"
    submission.reviewed_by = user.id if user else None
    if action == "approve":
        await add_points(
            session,
            user_id=submission.user_id,
            points=task.points,
            reason=f"Выполнение задания: {task.title}",
            approved_by=user.id if user else None,
            related_task_id=task.id,
        )
        await add_portfolio_item(
            session,
            user_id=submission.user_id,
            title=f"Выполненное задание: {task.title}",
            item_type="task",
            description=submission.text or task.description,
            issued_by=user.id if user else None,
            related_task_id=task.id,
        )
    await call.message.answer(
        "Результат принят и награда начислена"
        if action == "approve"
        else "Результат возвращён участнику"
    )
    if target:
        await safe_send(
            bot,
            target.telegram_id,
            f"Результат задания «{task.title}» "
            + (
                f"принят — начислено {task.points} баллов"
                if action == "approve"
                else "нужно дополнить. Откройте задание и отправьте обновлённый результат"
            ),
        )


@router.callback_query(F.data.regexp(r"^admin:task:(approve|revise):\d+$"))
async def decide_task(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, action, raw_id = call.data.split(":")
    task = await session.get(Task, int(raw_id))
    if task is None or task.status != "review":
        return
    target = await session.get(User, task.assignee_id)
    if action == "approve":
        task.status = "completed"
        await add_points(
            session,
            user_id=task.assignee_id,
            points=task.points,
            reason=f"Выполнение задачи: {task.title}",
            approved_by=user.id if user else None,
            related_task_id=task.id,
        )
        await add_portfolio_item(
            session,
            user_id=task.assignee_id,
            title=f"Выполненная задача: {task.title}",
            item_type="task",
            description=task.description,
            issued_by=user.id if user else None,
            related_task_id=task.id,
        )
        notice = f"Задача «{task.title}» подтверждена. Начислено баллов: {task.points}."
    else:
        task.status = "in_progress"
        notice = f"Задача «{task.title}» возвращена в работу. Уточните детали у лидера."
    await call.message.answer("Решение по задаче сохранено.")
    if target:
        await safe_send(bot, target.telegram_id, notice)


@router.callback_query(F.data == "admin:proposals")
async def proposals(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    items = (
        await session.scalars(
            select(Proposal)
            .where(Proposal.status == "pending")
            .order_by(Proposal.created_at)
        )
    ).all()
    if not items:
        await call.message.answer("Предложений лидеров на рассмотрении нет.")
        return
    for item in items:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Одобрить",
                        callback_data=f"admin:proposal:approve:{item.id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Отклонить",
                        callback_data=f"admin:proposal:reject:{item.id}",
                    )
                ],
            ]
        )
        await call.message.answer(
            f"Предложение #{item.id}\n\nТип: {item.proposal_type}\n"
            f"Значение: {item.payload.get('value')}\nПричина: {item.reason}",
            reply_markup=keyboard,
        )


@router.callback_query(F.data.regexp(r"^admin:proposal:(approve|reject):\d+$"))
async def decide_proposal(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, action, raw_id = call.data.split(":")
    item = await session.get(Proposal, int(raw_id))
    if item is None or item.status != "pending":
        return
    item.status = "approved" if action == "approve" else "rejected"
    item.reviewed_by = user.id if user else None
    target = await session.get(User, item.target_user_id)
    value = str(item.payload.get("value", ""))
    if action == "approve" and target:
        if item.proposal_type == "points":
            try:
                amount = int(value)
            except ValueError:
                amount = 0
            if amount:
                await add_points(
                    session,
                    user_id=target.id,
                    points=amount,
                    reason=item.reason,
                    approved_by=user.id if user else None,
                )
        elif item.proposal_type == "status" and value in {
            x.value for x in ParticipationStatus
        }:
            target.participation_status = value
        else:
            await add_portfolio_item(
                session,
                user_id=target.id,
                title=value or item.proposal_type,
                item_type=item.proposal_type,
                description=item.reason,
                issued_by=user.id if user else None,
            )
    await call.message.answer("Решение по предложению сохранено.")
    if target:
        await safe_send(
            bot,
            target.telegram_id,
            "Предложение лидера по Вашему участию одобрено."
            if action == "approve"
            else "Предложение лидера по Вашему участию сейчас не одобрено.",
        )


@router.callback_query(F.data == "admin:leader_broadcasts")
async def leader_broadcasts(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    items = (
        await session.scalars(
            select(Broadcast)
            .where(
                Broadcast.status == "pending", Broadcast.audience_type == "leader_scope"
            )
            .order_by(Broadcast.created_at)
        )
    ).all()
    if not items:
        await call.message.answer("Рассылок лидеров на утверждении нет.")
        return
    for item in items:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Одобрить и отправить",
                        callback_data=f"admin:lb:approve:{item.id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Отклонить", callback_data=f"admin:lb:reject:{item.id}"
                    )
                ],
            ]
        )
        await call.message.answer(
            f"Рассылка лидера #{item.id}\n\n{item.text}", reply_markup=keyboard
        )


@router.callback_query(F.data.regexp(r"^admin:lb:(approve|reject):\d+$"))
async def decide_leader_broadcast(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, action, raw_id = call.data.split(":")
    item = await session.get(Broadcast, int(raw_id))
    if item is None or item.status != "pending":
        return
    if action == "reject":
        item.status = "rejected"
        await call.message.answer("Рассылка отклонена.")
        return
    filters = item.audience_filter_json or {}
    department_ids = filters.get("department_ids", [])
    direction_ids = filters.get("direction_ids", [])
    query = (
        select(User)
        .outerjoin(UserDepartment)
        .outerjoin(UserDirection)
        .where(
            User.application_status == ApplicationStatus.APPROVED,
            or_(
                UserDepartment.department_id.in_(department_ids or [-1]),
                UserDirection.direction_id.in_(direction_ids or [-1]),
            ),
        )
    )
    recipients = (await session.scalars(query)).unique().all()
    sent, failed = await broadcast(bot, (x.telegram_id for x in recipients), item.text)
    item.status = "sent"
    item.sent_at = datetime.now().astimezone()
    await call.message.answer(
        f"Рассылка отправлена. Доставлено: {sent}. Ошибок: {failed}."
    )


@router.callback_query(F.data == "admin:settings")
async def settings_help(
    call: CallbackQuery, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user, settings):
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Канал ЭРА", callback_data="admin:bindchat:era_channel"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Общий чат", callback_data="admin:bindchat:general"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Внутренние связи", callback_data="admin:bindchat:internal"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Внешние связи", callback_data="admin:bindchat:external"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Чат лидеров", callback_data="admin:bindchat:leaders"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔗 Ссылки и приглашения",
                    callback_data="admin:setting_links",
                )
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="admin:menu:system")],
        ]
    )
    await call.message.answer(
        "⚙️ Подключение чатов\n\n"
        f"Канал ЭРА: {'подключён' if settings.era_channel_id else 'нужно подключить'}\n"
        f"Общий чат: {'подключён' if settings.general_chat_id else 'нужно подключить'}\n"
        f"Внутренние связи: {'подключён' if settings.internal_department_chat_id else 'нужно подключить'}\n"
        f"Внешние связи: {'подключён' if settings.external_department_chat_id else 'нужно подключить'}\n"
        f"Лидеры: {'подключён' if settings.leaders_chat_id else 'нужно подключить'}\n\n"
        "Числовой ID нужен боту для проверки подписки, приветствий и напоминаний",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "admin:setting_links")
async def setting_links(
    call: CallbackQuery, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user, settings):
        return
    rows = [
        [
            InlineKeyboardButton(
                text=label, callback_data=f"admin:setting_link:{short_key}"
            )
        ]
        for short_key, (label, _) in SETTING_LINK_KEYS.items()
    ]
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="admin:settings")])
    await call.message.answer(
        "🔗 Ссылки ЭРА\n\nВыберите ссылку, которую хотите изменить",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("admin:setting_link:"))
async def setting_link_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    short_key = call.data.rsplit(":", 1)[-1]
    item = SETTING_LINK_KEYS.get(short_key)
    if item is None:
        return
    label, setting_key = item
    await state.set_state(AdminSettingsStates.link_edit)
    await state.update_data(setting_link_key=setting_key)
    await call.message.answer(
        f"{label}\n\nСейчас:\n{getattr(settings, setting_key)}\n\n"
        "Пришлите новую ссылку, начинающуюся с https://"
    )


@router.message(AdminSettingsStates.link_edit)
async def setting_link_finish(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(message, user, settings):
        return
    value = (message.text or "").strip()
    if not value.startswith("https://") or len(value) > 500:
        await message.answer("Нужна корректная ссылка, начинающаяся с https://")
        return
    setting_key = (await state.get_data())["setting_link_key"]
    current = await session.scalar(
        select(AppSetting).where(AppSetting.key == setting_key)
    )
    if current:
        current.value = value
        current.updated_by = user.id if user else None
    else:
        session.add(
            AppSetting(
                key=setting_key,
                value=value,
                updated_by=user.id if user else None,
            )
        )
    setattr(settings, setting_key, value)
    await state.clear()
    await message.answer("Ссылка обновлена и уже используется ботом")


@router.callback_query(F.data == "admin:maintenance")
async def maintenance_preview(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    if call.from_user.id not in settings.admin_ids:
        await call.message.answer(
            "Очистка доступна только основному администратору ЭРА"
        )
        return
    counts = await reset_preview(session, settings.admin_ids)
    labels = {
        "users": "участников",
        "events": "мероприятий",
        "projects": "проектов",
        "tasks": "заданий",
        "points": "операций с баллами",
        "portfolio_items": "записей портфолио",
        "broadcasts": "рассылок",
        "user_questions": "вопросов",
        "audit_logs": "технических записей",
    }
    visible = [
        f"• {labels[name]}: {value}" for name, value in counts.items() if name in labels
    ]
    total = sum(counts.values())
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Продолжить очистку",
                    callback_data="admin:maintenance:confirm",
                )
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="admin:menu:system")],
        ]
    )
    await call.message.answer(
        "🧹 Очистка тестовых данных\n\n"
        + ("\n".join(visible) if visible else "Рабочих данных для удаления нет")
        + f"\n\nВсего связанных записей: {total}\n\n"
        "Будут сохранены: основной администратор, департаменты, направления, "
        "бейджи, должности, ссылки, ID чатов и тексты приветствий",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "admin:maintenance:confirm")
async def maintenance_confirm(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    if call.from_user.id not in settings.admin_ids:
        return
    await state.set_state(AdminMaintenanceStates.confirm)
    await call.message.answer(
        "Это действие нельзя отменить\n\n"
        "Чтобы удалить тестовых участников и всю рабочую историю, напишите точно:\n"
        "ОЧИСТИТЬ БАЗУ\n\n"
        "Любой другой ответ отменит операцию"
    )


@router.message(AdminMaintenanceStates.confirm)
async def maintenance_finish(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(message, user, settings):
        return
    if message.from_user.id not in settings.admin_ids:
        await state.clear()
        return
    if (message.text or "").strip() != "ОЧИСТИТЬ БАЗУ":
        await state.clear()
        await message.answer("Очистка отменена — данные не изменены")
        return
    counts = await reset_operational_data(session, settings.admin_ids)
    await state.clear()
    await message.answer(
        f"Готово — удалено {sum(counts.values())} связанных тестовых записей\n\n"
        "Ваш доступ, структура ЭРА и настройки сохранены. Можно начинать работу с чистой системой"
    )


@router.callback_query(F.data.startswith("admin:bindchat:"))
async def bind_chat_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    key = call.data.rsplit(":", 1)[-1]
    await state.set_state(AdminSettingsStates.chat_bind)
    await state.update_data(bind_chat_key=key)
    await call.message.answer(
        "Перешлите сюда любое сообщение из нужного канала или чата\n\n"
        "Для закрытого канала пересылка должна быть разрешена. Если она запрещена — временно включите её в настройках канала"
    )


@router.message(AdminSettingsStates.chat_bind)
async def bind_chat_finish(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(message, user, settings):
        return
    origin = message.forward_origin
    chat = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
    if chat is None:
        await message.answer(
            "Не удалось определить чат. Перешлите обычное сообщение непосредственно из нужного чата"
        )
        return
    key = (await state.get_data())["bind_chat_key"]
    mapping = {
        "era_channel": ("era_channel_id", "channel"),
        "general": ("general_chat_id", "general"),
        "internal": ("internal_department_chat_id", "internal"),
        "external": ("external_department_chat_id", "external"),
        "leaders": ("leaders_chat_id", "leaders"),
    }
    setting_key, greeting_key = mapping[key]
    setattr(settings, setting_key, chat.id)
    current = await session.scalar(
        select(AppSetting).where(AppSetting.key == setting_key)
    )
    if current:
        current.value = str(chat.id)
        current.updated_by = user.id if user else None
    else:
        session.add(
            AppSetting(
                key=setting_key,
                value=str(chat.id),
                updated_by=user.id if user else None,
            )
        )
    greeting = await session.scalar(
        select(ChatGreeting).where(ChatGreeting.chat_key == greeting_key)
    )
    if greeting:
        greeting.chat_id = chat.id
    await state.clear()
    await message.answer(
        f"Готово — «{chat.title or chat.username or 'чат'}» подключён к боту"
    )


@router.message(Command("setsetting"))
async def set_setting(
    message: Message,
    command: CommandObject,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(message, user, settings):
        return
    allowed = {
        "era_channel_url",
        "era_pro_channel_url",
        "general_chat_url",
        "internal_department_chat_url",
        "external_department_chat_url",
        "leaders_chat_url",
    }
    try:
        key, value = (command.args or "").split(maxsplit=1)
        if key not in allowed or not value.startswith(("https://", "http://")):
            raise ValueError
    except ValueError:
        await message.answer(
            "Формат: /setsetting имя_параметра https://ссылка. Список параметров находится в разделе «Настройки»."
        )
        return
    current = await session.scalar(select(AppSetting).where(AppSetting.key == key))
    if current:
        current.value = value
        current.updated_by = user.id if user else None
    else:
        session.add(
            AppSetting(key=key, value=value, updated_by=user.id if user else None)
        )
    setattr(settings, key, value)
    await audit(
        session,
        actor_id=user.id if user else None,
        action="setting.updated",
        entity_type="app_setting",
        new_value={"key": key, "value": value},
    )
    await message.answer("Настройка обновлена и уже используется ботом.")
