from aiogram import F, Bot, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import (
    Department,
    DepartmentApplication,
    Direction,
    Office,
    User,
    UserOffice,
)
from app.keyboards.common import options_keyboard
from app.keyboards.participant import department_keyboard, departments_keyboard
from app.services.audit_service import audit
from app.services.notification_service import notify_admins
from app.states.department import DepartmentApplicationStates
from app.utils import texts
from app.utils.constants import ApplicationStatus, DEPARTMENTS
from app.utils.validators import clean_text

router = Router(name="departments")


async def _send_team_menu(
    message: Message, user: User | None, settings: Settings
) -> None:
    if not user or user.application_status != ApplicationStatus.APPROVED:
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer(
        texts.DEPARTMENTS_OVERVIEW,
        reply_markup=departments_keyboard(settings.general_chat_url),
    )


@router.message(F.text == "🤝 Команда ЭРА")
@router.message(Command("team"), F.chat.type == "private")
@router.message(Command("departments"), F.chat.type == "private")
async def departments_menu_button(
    message: Message, user: User | None, settings: Settings, state: FSMContext
) -> None:
    await state.clear()
    await _send_team_menu(message, user, settings)


@router.callback_query(F.data == "departments:menu")
async def departments_menu(
    call: CallbackQuery, user: User | None, settings: Settings
) -> None:
    await call.answer()
    await call.message.edit_text(
        texts.DEPARTMENTS_OVERVIEW,
        reply_markup=departments_keyboard(settings.general_chat_url),
    )


@router.callback_query(F.data.startswith("department:view:"))
async def department_view(call: CallbackQuery, settings: Settings) -> None:
    await call.answer()
    key = call.data.rsplit(":", 1)[-1]
    if key == "internal":
        text, url = texts.INTERNAL_DEPARTMENT, settings.internal_department_chat_url
    else:
        text, url = texts.EXTERNAL_DEPARTMENT, settings.external_department_chat_url
    await call.message.edit_text(text, reply_markup=department_keyboard(url))


@router.callback_query(F.data == "team:offices")
async def team_offices(call: CallbackQuery, session: AsyncSession) -> None:
    await call.answer()
    rows = (
        await session.execute(
            select(Office, User)
            .join(UserOffice, UserOffice.office_id == Office.id)
            .join(User, User.id == UserOffice.user_id)
            .where(Office.is_active.is_(True), UserOffice.is_active.is_(True))
            .order_by(Office.sort_order, Office.title, User.first_name)
        )
    ).all()
    if not rows:
        await call.message.edit_text(
            "Команда должностных лиц сейчас формируется\n\nКонтакты появятся здесь после назначения",
            reply_markup=departments_keyboard(),
        )
        return
    lines = ["Кто отвечает за направления 👥"]
    buttons = []
    for office, holder in rows:
        name = f"{holder.first_name} {holder.last_name or ''}".strip()
        lines.append(f"\n{office.title}\n{name}")
        if holder.username and office.public_contact:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"Написать: {name}",
                        url=f"https://t.me/{holder.username}",
                    )
                ]
            )
    buttons.append(
        [InlineKeyboardButton(text="← Назад", callback_data="departments:menu")]
    )
    await call.message.edit_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data == "department:chats")
async def department_chats(call: CallbackQuery, settings: Settings) -> None:
    await call.answer()
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Чат внутренних связей",
                    url=settings.internal_department_chat_url,
                )
            ],
            [
                InlineKeyboardButton(
                    text="Чат внешних связей", url=settings.external_department_chat_url
                )
            ],
            [InlineKeyboardButton(text="Общий чат ЭРА", url=settings.general_chat_url)],
            [InlineKeyboardButton(text="Назад", callback_data="departments:menu")],
        ]
    )
    await call.message.answer(
        "Чаты департаментов\n\nВыберите чат своего направления.", reply_markup=keyboard
    )


@router.callback_query(F.data == "department:apply:start")
async def application_start(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    await state.set_state(DepartmentApplicationStates.department)
    await call.message.answer(
        "Выберите департамент для заявки.",
        reply_markup=options_keyboard(
            [(name, f"deptapp:dept:{index}") for index, name in enumerate(DEPARTMENTS)]
        ),
    )


@router.callback_query(
    DepartmentApplicationStates.department, F.data.startswith("deptapp:dept:")
)
async def application_department(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    names = tuple(DEPARTMENTS)
    try:
        department = names[int(call.data.rsplit(":", 1)[-1])]
    except (ValueError, IndexError):
        return
    await state.update_data(application_department=department)
    await state.set_state(DepartmentApplicationStates.direction)
    await call.message.answer(
        "Выберите направление.",
        reply_markup=options_keyboard(
            [
                (name, f"deptapp:dir:{index}")
                for index, name in enumerate(DEPARTMENTS[department])
            ]
        ),
    )


@router.callback_query(
    DepartmentApplicationStates.direction, F.data.startswith("deptapp:dir:")
)
async def application_direction(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    data = await state.get_data()
    directions = DEPARTMENTS[data["application_department"]]
    try:
        direction = directions[int(call.data.rsplit(":", 1)[-1])]
    except (ValueError, IndexError):
        return
    await state.update_data(application_direction=direction)
    await state.set_state(DepartmentApplicationStates.motivation)
    await call.message.answer(texts.DEPARTMENT_APPLICATION_MOTIVATION)


@router.message(DepartmentApplicationStates.motivation)
async def application_motivation(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 1500)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(application_motivation=value)
    await state.set_state(DepartmentApplicationStates.usefulness)
    await message.answer(texts.DEPARTMENT_APPLICATION_USEFULNESS)


@router.message(DepartmentApplicationStates.usefulness)
async def application_usefulness(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 1500)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(application_usefulness=value)
    await state.set_state(DepartmentApplicationStates.available_time)
    await message.answer(texts.DEPARTMENT_APPLICATION_TIME)


@router.message(DepartmentApplicationStates.available_time)
async def application_finish(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    settings: Settings,
) -> None:
    value = clean_text(message.text or "", 255)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    data = await state.get_data()
    department = await session.scalar(
        select(Department).where(Department.name == data["application_department"])
    )
    direction = await session.scalar(
        select(Direction).where(Direction.name == data["application_direction"])
    )
    application = DepartmentApplication(
        user_id=user.id,
        department_id=department.id,
        direction_id=direction.id,
        motivation=data["application_motivation"],
        usefulness=data["application_usefulness"],
        available_time=value,
    )
    session.add(application)
    await session.flush()
    await audit(
        session,
        actor_id=user.id,
        action="department.application_created",
        entity_type="department_application",
        entity_id=application.id,
    )
    await state.clear()
    await message.answer(texts.DEPARTMENT_APPLICATION_DONE)
    await notify_admins(
        bot,
        settings,
        f"Новая заявка в департамент: {department.name}, {direction.name}. "
        f"Участник: {user.first_name} {user.last_name or ''}.",
    )
