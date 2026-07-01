from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Bot, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import (
    Broadcast,
    Department,
    Direction,
    Event,
    Project,
    Proposal,
    Report,
    Task,
    User,
    UserDepartment,
    UserDirection,
)
from app.keyboards.common import options_keyboard
from app.keyboards.leader import leader_panel_keyboard
from app.services.ai_service import AIService, AIUnavailableError
from app.services.audit_service import audit
from app.services.notification_service import notify_admins
from app.states.event import EventStates
from app.states.task import BroadcastStates, ProposalStates, ReportStates, TaskStates
from app.utils import texts
from app.utils.constants import (
    ApplicationStatus,
    EVENT_STATUS_LABELS,
    EventStatus,
    PRIVILEGED_ROLES,
    PROJECT_STATUS_LABELS,
    STATUS_LABELS,
    TASK_STATUS_LABELS,
    Role,
)
from app.utils.telegram import send_long_text
from app.utils.validators import clean_text, parse_date, parse_time

router = Router(name="leader")


async def _guard(event: Message | CallbackQuery, user: User | None) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
    else:
        message = event
    if not user or user.is_blocked or user.role not in PRIVILEGED_ROLES:
        await message.answer(texts.NO_ACCESS)
        return False
    return True


def _scope_ids(user: User) -> tuple[set[int], set[int]]:
    return (
        {item.department_id for item in user.departments},
        {item.direction_id for item in user.directions},
    )


@router.message(Command("leader"))
@router.message(F.text == "🧭 Панель лидера")
async def leader_command(
    message: Message, user: User | None, state: FSMContext
) -> None:
    if not await _guard(message, user):
        return
    await state.clear()
    await message.answer(texts.LEADER_PANEL, reply_markup=leader_panel_keyboard())


@router.callback_query(F.data == "leader:panel")
async def leader_panel(call: CallbackQuery, user: User | None) -> None:
    if not await _guard(call, user):
        return
    await call.message.answer(texts.LEADER_PANEL, reply_markup=leader_panel_keyboard())


@router.callback_query(F.data == "leader:department")
async def leader_department(call: CallbackQuery, user: User | None) -> None:
    if not await _guard(call, user):
        return
    departments = (
        "\n".join(f"• {item.department.name}" for item in user.departments)
        or "• Не закреплён"
    )
    directions = (
        "\n".join(f"• {item.direction.name}" for item in user.directions)
        or "• Не закреплён"
    )
    await call.message.answer(
        f"Ваши департаменты\n{departments}\n\nВаши направления\n{directions}"
    )


@router.callback_query(F.data == "leader:participants")
async def leader_participants(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    if user.role == Role.ADMIN:
        query = select(User).where(
            User.application_status == ApplicationStatus.APPROVED
        )
    else:
        department_ids, direction_ids = _scope_ids(user)
        query = (
            select(User)
            .outerjoin(UserDepartment)
            .outerjoin(UserDirection)
            .where(
                User.application_status == ApplicationStatus.APPROVED,
                or_(
                    UserDepartment.department_id.in_(department_ids or {-1}),
                    UserDirection.direction_id.in_(direction_ids or {-1}),
                ),
            )
        )
    participants = (
        (await session.scalars(query.order_by(User.first_name))).unique().all()
    )
    body = (
        "\n".join(
            f"• {item.first_name} {item.last_name or ''} — "
            f"{STATUS_LABELS.get(item.participation_status, 'Статус уточняется')}"
            for item in participants
        )
        or "Участников в Вашем контуре пока нет."
    )
    await send_long_text(call.message, body)


@router.callback_query(F.data == "leader:events")
async def leader_events(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    query = select(Event)
    if user.role != Role.ADMIN:
        department_ids, direction_ids = _scope_ids(user)
        query = query.where(
            or_(
                Event.department_id.in_(department_ids or {-1}),
                Event.direction_id.in_(direction_ids or {-1}),
                Event.created_by == user.id,
            )
        )
    events = (
        await session.scalars(query.order_by(Event.event_date.desc()).limit(30))
    ).all()
    body = (
        "\n".join(
            f"• #{x.id} {x.title} — {EVENT_STATUS_LABELS.get(x.status, 'Статус уточняется')}"
            for x in events
        )
        or "Мероприятий пока нет."
    )
    await call.message.answer(body)


@router.callback_query(F.data == "leader:event:new")
async def event_new_menu(call: CallbackQuery, user: User | None) -> None:
    if not await _guard(call, user):
        return
    await call.message.answer(
        "Как подготовить мероприятие?",
        reply_markup=options_keyboard(
            [
                ("С помощью ИИ", "leader:event:mode:ai"),
                ("Вручную", "leader:event:mode:manual"),
            ]
        ),
    )


@router.callback_query(F.data.startswith("leader:event:mode:"))
async def event_mode(call: CallbackQuery, state: FSMContext, user: User | None) -> None:
    if not await _guard(call, user):
        return
    use_ai = call.data.endswith(":ai")
    await state.clear()
    await state.update_data(event_use_ai=use_ai)
    if use_ai:
        await state.set_state(EventStates.idea)
        await call.message.answer(
            "Опишите идею мероприятия. ИИ предложит концепцию, программу, команду и анонс."
        )
    else:
        await state.set_state(EventStates.title)
        await call.message.answer("Напишите название мероприятия.")


@router.message(EventStates.idea)
async def event_idea(
    message: Message, state: FSMContext, ai_service: AIService
) -> None:
    idea = clean_text(message.text or "", 2000)
    if not idea:
        await message.answer(texts.INVALID_INPUT)
        return
    try:
        plan = await ai_service.generate_event_plan({"idea": idea})
    except AIUnavailableError:
        plan = f"Концепция мероприятия\n\n{idea}\n\nДополните описание, программу и ресурсы вручную."
    await state.update_data(event_idea=idea, event_ai_plan=plan)
    await state.set_state(EventStates.title)
    await send_long_text(
        message,
        f"Предварительная концепция:\n\n{plan}\n\nТеперь напишите итоговое название.",
    )


@router.message(EventStates.title)
async def event_title(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 255)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(event_title=value)
    await state.set_state(EventStates.description)
    await message.answer("Напишите описание мероприятия.")


@router.message(EventStates.description)
async def event_description(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 3000)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(event_description=value)
    await state.set_state(EventStates.event_date)
    await message.answer("Укажите дату в формате ДД.ММ.ГГГГ.")


@router.message(EventStates.event_date)
async def event_date_step(message: Message, state: FSMContext) -> None:
    value = parse_date(message.text or "")
    if value is None:
        await message.answer("Проверьте дату. Формат: ДД.ММ.ГГГГ.")
        return
    await state.update_data(event_date=value)
    await state.set_state(EventStates.event_time)
    await message.answer("Укажите время в формате ЧЧ:ММ.")


@router.message(EventStates.event_time)
async def event_time_step(message: Message, state: FSMContext) -> None:
    value = parse_time(message.text or "")
    if value is None:
        await message.answer("Проверьте время. Формат: ЧЧ:ММ.")
        return
    await state.update_data(event_time=value)
    await state.set_state(EventStates.location)
    await message.answer("Укажите место проведения.")


@router.message(EventStates.location)
async def event_location(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 255)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(event_location=value)
    await state.set_state(EventStates.department)
    await message.answer(
        "Выберите департамент.",
        reply_markup=options_keyboard(
            [
                ("Внутренние связи", "event:dept:internal"),
                ("Внешние связи", "event:dept:external"),
            ]
        ),
    )


@router.callback_query(EventStates.department, F.data.startswith("event:dept:"))
async def event_department(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    key = call.data.rsplit(":", 1)[-1]
    department = "Внутренние связи" if key == "internal" else "Внешние связи"
    await state.update_data(event_department=department, event_department_key=key)
    await state.set_state(EventStates.direction)
    options = (
        (("Лидерство", "lead"), ("Культура", "culture"), ("Интерактив", "interactive"))
        if key == "internal"
        else (
            ("Международное направление", "international"),
            ("Медиа", "media"),
            ("Социальные инициативы", "social"),
        )
    )
    await call.message.answer(
        "Выберите направление.",
        reply_markup=options_keyboard(
            [(label, f"event:dir:{value}") for label, value in options]
        ),
    )


@router.callback_query(EventStates.direction, F.data.startswith("event:dir:"))
async def event_direction(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    key = call.data.rsplit(":", 1)[-1]
    value = {
        "lead": "Лидерство",
        "culture": "Культура",
        "interactive": "Интерактив",
        "international": "Международное направление",
        "media": "Медиа",
        "social": "Социальные инициативы",
    }.get(key)
    if not value:
        return
    await state.update_data(event_direction=value)
    await state.set_state(EventStates.format)
    await call.message.answer("Укажите формат мероприятия.")


@router.message(EventStates.format)
async def event_format(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 100)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(event_format=value)
    await state.set_state(EventStates.participant_limit)
    await message.answer(
        "Укажите лимит участников числом. Если лимита нет, отправьте 0."
    )


@router.message(EventStates.participant_limit)
async def event_limit(message: Message, state: FSMContext) -> None:
    try:
        value = int(message.text or "")
        if value < 0:
            raise ValueError
    except ValueError:
        await message.answer("Укажите целое число от 0.")
        return
    await state.update_data(event_limit=value or None)
    await state.set_state(EventStates.points)
    await message.answer("Сколько баллов предусмотрено за подтверждённое участие?")


@router.message(EventStates.points)
async def event_points(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    settings: Settings,
) -> None:
    try:
        value = int(message.text or "")
        if not 0 <= value <= 1000:
            raise ValueError
    except ValueError:
        await message.answer("Укажите число от 0 до 1000.")
        return
    await state.update_data(event_points=value)
    data = await state.get_data()
    department = await session.scalar(
        select(Department).where(Department.name == data["event_department"])
    )
    direction = await session.scalar(
        select(Direction).where(Direction.name == data["event_direction"])
    )
    event = Event(
        title=data["event_title"],
        description=data["event_description"],
        event_date=data["event_date"],
        event_time=data["event_time"],
        location=data["event_location"],
        department_id=department.id,
        direction_id=direction.id,
        format=data["event_format"],
        responsible_id=user.id,
        participant_limit=data["event_limit"],
        points_for_visit=data["event_points"],
        selfie_required=False,
        additional_info=data.get("event_ai_plan"),
        status=EventStatus.PENDING_APPROVAL,
        created_by=user.id,
    )
    session.add(event)
    await session.flush()
    await audit(
        session,
        actor_id=user.id,
        action="event.submitted",
        entity_type="event",
        entity_id=event.id,
    )
    await state.clear()
    await message.answer(
        "Мероприятие отправлено администратору на утверждение\n\n"
        "После завершения администратор сможет отдельно открыть активности: отзыв, фото, видео или задание с собственной наградой"
    )
    await notify_admins(
        bot, settings, f"Мероприятие на утверждении: {event.title} (#{event.id})."
    )


@router.callback_query(F.data == "leader:projects")
async def leader_projects(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    query = select(Project)
    if user.role != Role.ADMIN:
        department_ids, direction_ids = _scope_ids(user)
        query = query.where(
            or_(
                Project.department_id.in_(department_ids or {-1}),
                Project.direction_id.in_(direction_ids or {-1}),
            )
        )
    projects = (
        await session.scalars(query.order_by(Project.created_at.desc()).limit(30))
    ).all()
    body = (
        "\n".join(
            f"• #{x.id} {x.title} — {PROJECT_STATUS_LABELS.get(x.status, 'Статус уточняется')}"
            for x in projects
        )
        or "Проектов пока нет."
    )
    await call.message.answer(body)


@router.callback_query(F.data == "leader:task:new")
async def task_start(call: CallbackQuery, state: FSMContext, user: User | None) -> None:
    if not await _guard(call, user):
        return
    await state.clear()
    await state.set_state(TaskStates.assignee)
    await call.message.answer(
        "Кому назначить задачу? Напишите имя, фамилию, @username или Telegram ID"
    )


@router.message(TaskStates.assignee)
async def task_assignee(
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
        await message.answer("Участник не найден — попробуйте другое написание")
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{target.first_name} {target.last_name or ''}".strip(),
                    callback_data=f"leader:task:assignee:{target.id}",
                )
            ]
            for target in targets
        ]
    )
    await message.answer("Выберите участника", reply_markup=keyboard)


@router.callback_query(TaskStates.assignee, F.data.startswith("leader:task:assignee:"))
async def task_assignee_selected(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(task_assignee_id=int(call.data.rsplit(":", 1)[-1]))
    await state.set_state(TaskStates.title)
    await call.message.answer("Напишите короткое название задачи")


@router.message(TaskStates.title)
async def task_title(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 255)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(task_title=value)
    await state.set_state(TaskStates.description)
    await message.answer("Опишите задачу и ожидаемый результат.")


@router.message(TaskStates.description)
async def task_description(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 2000)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(task_description=value)
    await state.set_state(TaskStates.deadline)
    await message.answer("Укажите дедлайн: ДД.ММ.ГГГГ ЧЧ:ММ.")


@router.message(TaskStates.deadline)
async def task_deadline(
    message: Message, state: FSMContext, settings: Settings
) -> None:
    try:
        value = datetime.strptime(message.text or "", "%d.%m.%Y %H:%M").replace(
            tzinfo=ZoneInfo(settings.timezone)
        )
    except ValueError:
        await message.answer("Проверьте формат: ДД.ММ.ГГГГ ЧЧ:ММ.")
        return
    await state.update_data(task_deadline=value)
    await state.set_state(TaskStates.points)
    await message.answer("Укажите количество баллов после подтверждения задачи.")


@router.message(TaskStates.points)
async def task_finish(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    try:
        points = int(message.text or "")
        if not 0 <= points <= 1000:
            raise ValueError
    except ValueError:
        await message.answer("Укажите число от 0 до 1000.")
        return
    data = await state.get_data()
    task = Task(
        title=data["task_title"],
        description=data["task_description"],
        assignee_id=data["task_assignee_id"],
        creator_id=user.id,
        deadline=data["task_deadline"],
        points=points,
    )
    session.add(task)
    await session.flush()
    target = await session.get(User, task.assignee_id)
    if target:
        from app.services.notification_service import safe_send

        await safe_send(
            bot,
            target.telegram_id,
            f"У Вас новая задача ЭРА.\n\n{task.title}\n{task.description}\n\nДедлайн: {task.deadline:%d.%m.%Y %H:%M}",
        )
    await audit(
        session,
        actor_id=user.id,
        action="task.created",
        entity_type="task",
        entity_id=task.id,
    )
    await state.clear()
    await message.answer("Задача создана и отправлена исполнителю.")


@router.callback_query(F.data == "leader:tasks")
async def leader_tasks(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    tasks = (
        await session.scalars(
            select(Task)
            .where(Task.creator_id == user.id)
            .order_by(Task.deadline)
            .limit(30)
        )
    ).all()
    body = (
        "\n".join(
            f"• #{x.id} {x.title} — {TASK_STATUS_LABELS.get(x.status, 'Статус уточняется')}"
            for x in tasks
        )
        or "Созданных задач пока нет."
    )
    await call.message.answer(body)


@router.callback_query(F.data == "leader:proposal:new")
async def proposal_start(
    call: CallbackQuery, state: FSMContext, user: User | None
) -> None:
    if not await _guard(call, user):
        return
    await state.clear()
    await state.set_state(ProposalStates.proposal_type)
    options = (
        ("Предложить баллы", "points"),
        ("Повышение статуса", "status"),
        ("Назначение на должность", "office"),
        ("Знак отличия", "badge"),
        ("Документ в портфолио", "portfolio"),
    )
    await call.message.answer(
        "Выберите тип предложения.",
        reply_markup=options_keyboard(
            [(label, f"proposal:type:{key}") for label, key in options]
        ),
    )


@router.callback_query(
    ProposalStates.proposal_type, F.data.startswith("proposal:type:")
)
async def proposal_type(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(proposal_type=call.data.rsplit(":", 1)[-1])
    await state.set_state(ProposalStates.target)
    await call.message.answer(
        "Кого Вы хотите предложить? Напишите имя, фамилию, @username или Telegram ID"
    )


@router.message(ProposalStates.target)
async def proposal_target(
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
        await message.answer("Участник не найден — попробуйте другое написание")
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{target.first_name} {target.last_name or ''}".strip(),
                    callback_data=f"leader:proposal:target:{target.id}",
                )
            ]
            for target in targets
        ]
    )
    await message.answer("Выберите участника", reply_markup=keyboard)


@router.callback_query(
    ProposalStates.target, F.data.startswith("leader:proposal:target:")
)
async def proposal_target_selected(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(proposal_target_id=int(call.data.rsplit(":", 1)[-1]))
    await state.set_state(ProposalStates.value)
    await call.message.answer(
        "Напишите предлагаемое значение: количество баллов, статус, знак или вид поддержки."
    )


@router.message(ProposalStates.value)
async def proposal_value(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 500)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(proposal_value=value)
    await state.set_state(ProposalStates.reason)
    await message.answer("Объясните причину предложения.")


@router.message(ProposalStates.reason)
async def proposal_finish(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    settings: Settings,
) -> None:
    reason = clean_text(message.text or "", 1500)
    if not reason:
        await message.answer(texts.INVALID_INPUT)
        return
    data = await state.get_data()
    proposal = Proposal(
        proposer_id=user.id,
        target_user_id=data["proposal_target_id"],
        proposal_type=data["proposal_type"],
        payload={"value": data["proposal_value"]},
        reason=reason,
    )
    session.add(proposal)
    await session.flush()
    await state.clear()
    await message.answer("Предложение отправлено администратору.")
    await notify_admins(
        bot,
        settings,
        f"Новое предложение лидера #{proposal.id}: {proposal.proposal_type}.",
    )


@router.callback_query(F.data == "leader:reports")
async def report_start(
    call: CallbackQuery, state: FSMContext, user: User | None
) -> None:
    if not await _guard(call, user):
        return
    await state.clear()
    await state.set_state(ReportStates.report_type)
    await call.message.answer(
        "Выберите тип отчёта.",
        reply_markup=options_keyboard(
            [
                ("Отчёт по мероприятию", "report:type:event"),
                ("Месячный отчёт лидера", "report:type:monthly"),
            ]
        ),
    )


@router.callback_query(ReportStates.report_type, F.data.startswith("report:type:"))
async def report_type(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(report_type=call.data.rsplit(":", 1)[-1])
    await state.set_state(ReportStates.content)
    await call.message.answer(
        "Напишите факты, результаты, проблемы, выводы и следующие действия. Можно использовать свободную форму."
    )


@router.message(ReportStates.content)
async def report_finish(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    settings: Settings,
) -> None:
    content = clean_text(message.text or "", 6000)
    if not content:
        await message.answer(texts.INVALID_INPUT)
        return
    data = await state.get_data()
    report = Report(
        report_type=data["report_type"],
        author_id=user.id,
        month=datetime.now().strftime("%Y-%m"),
        content_json={"text": content},
    )
    session.add(report)
    await session.flush()
    await state.clear()
    await message.answer("Отчёт отправлен на рассмотрение.")
    await notify_admins(
        bot, settings, f"Новый отчёт #{report.id} от {user.first_name}."
    )


@router.callback_query(F.data == "leader:broadcast:new")
async def leader_broadcast_start(
    call: CallbackQuery, state: FSMContext, user: User | None
) -> None:
    if not await _guard(call, user):
        return
    await state.clear()
    await state.set_state(BroadcastStates.text)
    await call.message.answer(
        "Напишите текст рассылки для Вашего департамента или направления."
    )


@router.message(BroadcastStates.text)
async def leader_broadcast_finish(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    settings: Settings,
) -> None:
    value = clean_text(message.text or "", 3500)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    department_ids, direction_ids = _scope_ids(user)
    item = Broadcast(
        title="Рассылка лидера",
        text=value,
        audience_type="leader_scope",
        audience_filter_json={
            "department_ids": sorted(department_ids),
            "direction_ids": sorted(direction_ids),
        },
        author_id=user.id,
        status="pending",
    )
    session.add(item)
    await session.flush()
    await state.clear()
    await message.answer("Рассылка отправлена администратору на утверждение.")
    await notify_admins(
        bot, settings, f"Рассылка лидера #{item.id} ожидает утверждения."
    )
