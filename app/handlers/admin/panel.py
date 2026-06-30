from datetime import datetime

from aiogram import F, Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import (
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
    AppSetting,
    Badge,
    Broadcast,
    Department,
    DepartmentApplication,
    Direction,
    Event,
    EventRegistration,
    Project,
    Proposal,
    Report,
    Task,
    User,
    UserBadge,
    UserDepartment,
    UserDirection,
    UserQuestion,
)
from app.keyboards.admin import (
    admin_activity_keyboard,
    admin_communications_keyboard,
    admin_growth_keyboard,
    admin_panel_keyboard,
    admin_system_keyboard,
    admin_users_keyboard,
    application_actions,
    applications_keyboard,
    entity_actions,
)
from app.keyboards.participant import main_menu
from app.services.audit_service import audit
from app.services.notification_service import broadcast, safe_send
from app.services.points_service import add_points, add_portfolio_item
from app.states.admin import AdminAnswerStates, AdminBroadcastStates, AdminReviewStates
from app.utils import texts
from app.utils.constants import (
    ApplicationStatus,
    EventStatus,
    ParticipationStatus,
    ProjectStatus,
    REPORT_STATUS_LABELS,
    REPORT_TYPE_LABELS,
    RegistrationStatus,
    ROLE_LABELS,
    Role,
)
from app.utils.telegram import send_long_text
from app.utils.validators import clean_text

router = Router(name="admin")


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked)
    )


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
    if not _is_admin(user, settings, telegram_id):
        await message.answer(texts.NO_ACCESS)
        return False
    return True


@router.message(Command("admin"))
async def admin_command(
    message: Message, user: User | None, settings: Settings
) -> None:
    if not await _guard(message, user, settings):
        return
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
    body = f"""Заявка #{target.id}

{target.first_name} {target.last_name or ""}, {target.age or "—"}
Город: {target.city or "—"}
Телефон: {target.phone or "—"}
Учёба / работа: {target.education_work or "—"}
Занятие: {target.occupation or "—"}
Департаменты: {departments}
Направления: {directions}
Время: {target.available_time or "—"}
Опыт: {target.experience or "—"}
Путь: {target.desired_path or "—"}
Мотивация: {target.motivation or "—"}"""
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
    await call.message.answer("Заявка одобрена.")
    await safe_send(
        bot,
        target.telegram_id,
        texts.APPLICATION_APPROVED,
        main_menu(settings.era_channel_url),
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
            select(Event)
            .where(Event.status == EventStatus.PENDING_APPROVAL)
            .order_by(Event.created_at)
        )
    ).all()
    if not events:
        await call.message.answer("Мероприятий на утверждении нет.")
        return
    for event in events:
        await call.message.answer(
            f"Мероприятие #{event.id}\n\n{event.title}\n{event.event_date:%d.%m.%Y} {event.event_time:%H:%M}\n{event.description}",
            reply_markup=entity_actions("event", event.id),
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
            .where(Project.status == ProjectStatus.PENDING_REVIEW)
            .order_by(Project.created_at)
        )
    ).all()
    if not projects:
        await call.message.answer("Проектов на рассмотрении нет.")
        return
    for project in projects:
        await send_long_text(
            call.message,
            f"Проект #{project.id}\n\n{project.generated_document or project.short_description}",
            reply_markup=entity_actions("project", project.id),
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
@router.callback_query(F.data.startswith("admin:project:approve:"))
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
    entity = await session.get(Event if kind == "event" else Project, entity_id)
    if entity is None:
        return
    entity.status = EventStatus.PUBLISHED if kind == "event" else ProjectStatus.APPROVED
    entity.approved_by = (
        user.id if kind == "event" and user else getattr(entity, "approved_by", None)
    )
    await audit(
        session,
        actor_id=user.id if user else None,
        action=f"{kind}.approved",
        entity_type=kind,
        entity_id=entity_id,
    )
    await call.message.answer("Решение сохранено: одобрено.")
    owner_id = entity.created_by if kind == "event" else entity.author_id
    owner = await session.get(User, owner_id)
    if owner:
        if kind == "project":
            await add_points(
                session,
                user_id=owner.id,
                points=30,
                reason=f"Одобренный проект: {entity.title}",
                approved_by=user.id if user else None,
                related_project_id=entity.id,
            )
            await add_portfolio_item(
                session,
                user_id=owner.id,
                title=f"Одобренный проект: {entity.title}",
                item_type="project",
                description=entity.short_description,
                issued_by=user.id if user else None,
                related_project_id=entity.id,
            )
        notice = (
            f"Мероприятие «{entity.title}» одобрено и опубликовано."
            if kind == "event"
            else texts.PROJECT_APPROVED
        )
        await safe_send(bot, owner.telegram_id, notice)
    if kind == "event" and settings.general_chat_id:
        await safe_send(
            bot,
            settings.general_chat_id,
            f"Новое мероприятие ЭРА\n\n{entity.title}\n"
            f"{entity.event_date:%d.%m.%Y} в {entity.event_time:%H:%M}\n"
            f"Место: {entity.location}\n\n{entity.description}",
        )


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
                entity.status = (
                    ProjectStatus.NEEDS_REVISION
                    if action == "revise"
                    else ProjectStatus.REJECTED
                )
                owner = await session.get(User, entity.author_id)
                if owner:
                    template = (
                        texts.PROJECT_REVISION
                        if action == "revise"
                        else texts.PROJECT_REJECTED
                    )
                    await safe_send(
                        bot, owner.telegram_id, template.format(comment=comment)
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
    call: CallbackQuery, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.answer(
        "Чтобы добавить достижение, используйте команду:\n"
        "/portfolio Telegram_ID | тип | название | описание"
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
    call: CallbackQuery, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.answer(
        "Команды управления:\n"
        "/addpoints Telegram_ID количество причина\n"
        "/awardbadge Telegram_ID | название знака | причина"
    )


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
        "Команды управления:\n"
        "/setrole Telegram_ID participant|activist|leader|council|admin\n"
        "/setstatus Telegram_ID new_member|involved_member|active_member|team_member|project_curator|community_leader"
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
    users = (
        await session.scalars(
            select(User)
            .where(User.application_status == ApplicationStatus.APPROVED)
            .order_by(User.first_name)
            .limit(100)
        )
    ).all()
    body = "\n".join(
        f"• {x.first_name} {x.last_name or ''} — "
        f"{ROLE_LABELS.get(x.role, 'Роль уточняется')}, {x.telegram_id}"
        for x in users
    )
    await send_long_text(call.message, body or "Участников пока нет.")


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
        f"Селфи на проверке: {await count(AttendanceProof, AttendanceProof.status == 'pending')}"
    )
    await call.message.answer(body)


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
        ]
    )
    await call.message.answer("Выберите аудиторию рассылки.", reply_markup=keyboard)


@router.callback_query(
    AdminBroadcastStates.audience, F.data.startswith("broadcast:audience:")
)
async def broadcast_audience(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    audience = call.data.rsplit(":", 1)[-1]
    await state.update_data(broadcast_audience=audience)
    if audience == "all":
        await state.set_state(AdminBroadcastStates.text)
        await call.message.answer("Напишите текст рассылки.")
    else:
        await state.set_state(AdminBroadcastStates.filter_value)
        await call.message.answer("Напишите точное значение фильтра.")


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
        query = (
            query.join(UserDepartment)
            .join(UserDepartment.department)
            .where(UserDepartment.department.has(name=filter_value))
        )
    elif audience == "direction":
        query = query.join(UserDirection).where(
            UserDirection.direction.has(name=filter_value)
        )
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
    tasks = (
        await session.scalars(
            select(Task).where(Task.status == "review").order_by(Task.updated_at)
        )
    ).all()
    if not tasks:
        await call.message.answer("Задач на проверке нет.")
        return
    for task in tasks:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Подтвердить",
                        callback_data=f"admin:task:approve:{task.id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Вернуть в работу",
                        callback_data=f"admin:task:revise:{task.id}",
                    )
                ],
            ]
        )
        await call.message.answer(
            f"Задача #{task.id}\n\n{task.title}\n{task.description}\nБаллы: {task.points}",
            reply_markup=keyboard,
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
    await call.message.answer(
        "Основные ссылки и идентификаторы задаются в .env. Ссылки можно изменить без перезапуска командой:\n"
        "/setsetting имя_параметра новое_значение\n\n"
        "Допустимые параметры: era_channel_url, era_pro_channel_url, general_chat_url, "
        "internal_department_chat_url, external_department_chat_url, leaders_chat_url."
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
