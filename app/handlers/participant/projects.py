from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Project, User
from app.keyboards.common import options_keyboard
from app.keyboards.participant import project_menu_keyboard, project_result_keyboard
from app.services.ai_service import (
    AIService,
    AIUnavailableError,
    fallback_project_document,
)
from app.services.audit_service import audit
from app.services.notification_service import notify_admins
from app.services.project_service import create_project
from app.states.project import ProjectRevisionStates, ProjectStates
from app.utils import texts
from app.utils.constants import ApplicationStatus, ProjectStatus
from app.utils.telegram import send_long_text
from app.utils.validators import clean_text

router = Router(name="projects")


@router.callback_query(F.data == "projects:menu")
async def projects_menu(call: CallbackQuery, user: User | None) -> None:
    await call.answer()
    if not user or user.application_status != ApplicationStatus.APPROVED:
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    await call.message.answer(texts.PROJECT_MENU, reply_markup=project_menu_keyboard())


@router.callback_query(F.data.startswith("project:new:"))
async def project_start(
    call: CallbackQuery, state: FSMContext, user: User | None
) -> None:
    await call.answer()
    if not user or user.application_status != ApplicationStatus.APPROVED:
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    await state.clear()
    await state.update_data(use_ai=call.data.endswith(":ai"))
    await state.set_state(ProjectStates.idea)
    await call.message.answer(f"{texts.PROJECT_INTRO}\n\n{texts.PROJECT_STEPS[0]}")


@router.message(ProjectStates.idea)
async def project_idea(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 2000)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(idea=value)
    await state.set_state(ProjectStates.department)
    await message.answer(
        texts.PROJECT_STEPS[1],
        reply_markup=options_keyboard(
            [
                ("Внутренние связи", "project:dept:internal"),
                ("Внешние связи", "project:dept:external"),
                ("Не уверен", "project:dept:unsure"),
            ]
        ),
    )


@router.callback_query(ProjectStates.department, F.data.startswith("project:dept:"))
async def project_department(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    key = call.data.rsplit(":", 1)[-1]
    department = {
        "internal": "Внутренние связи",
        "external": "Внешние связи",
        "unsure": "Не определён",
    }.get(key)
    if department is None:
        return
    await state.update_data(department=department, project_department_key=key)
    await state.set_state(ProjectStates.direction)
    if key == "internal":
        options = [
            (x, f"project:dir:{k}")
            for x, k in (
                ("Лидерство", "lead"),
                ("Культура", "culture"),
                ("Интерактив", "interactive"),
                ("Не уверен", "unsure"),
            )
        ]
    elif key == "external":
        options = [
            (x, f"project:dir:{k}")
            for x, k in (
                ("Международное направление", "international"),
                ("Медиа", "media"),
                ("Социальные инициативы", "social"),
                ("Не уверен", "unsure"),
            )
        ]
    else:
        options = [("Не уверен", "project:dir:unsure")]
    await call.message.answer(
        texts.PROJECT_STEPS[2], reply_markup=options_keyboard(options)
    )


@router.callback_query(ProjectStates.direction, F.data.startswith("project:dir:"))
async def project_direction(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    key = call.data.rsplit(":", 1)[-1]
    direction = {
        "lead": "Лидерство",
        "culture": "Культура",
        "interactive": "Интерактив",
        "international": "Международное направление",
        "media": "Медиа",
        "social": "Социальные инициативы",
        "unsure": "Не определено",
    }.get(key)
    if direction is None:
        return
    await state.update_data(direction=direction)
    await state.set_state(ProjectStates.target_audience)
    options = [
        (label, f"project:audience:{index}")
        for index, label in enumerate(
            (
                "Новые участники",
                "Активисты ЭРА",
                "Студенты",
                "Школьники",
                "Молодёжь 16–25",
                "Команда ЭРА",
                "Другое",
            )
        )
    ]
    await call.message.answer(
        texts.PROJECT_STEPS[3], reply_markup=options_keyboard(options)
    )


@router.callback_query(
    ProjectStates.target_audience, F.data.startswith("project:audience:")
)
async def project_audience(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    values = (
        "Новые участники",
        "Активисты ЭРА",
        "Студенты",
        "Школьники",
        "Молодёжь 16–25",
        "Команда ЭРА",
        "Другое",
    )
    try:
        value = values[int(call.data.rsplit(":", 1)[-1])]
    except (ValueError, IndexError):
        return
    await state.update_data(target_audience=value)
    await state.set_state(ProjectStates.relevance)
    await call.message.answer(texts.PROJECT_STEPS[4])


async def _text_step(
    message: Message, state: FSMContext, key: str, next_state, next_prompt: str
) -> None:
    value = clean_text(message.text or "", 3000)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(**{key: value})
    await state.set_state(next_state)
    await message.answer(next_prompt)


@router.message(ProjectStates.relevance)
async def project_relevance(message: Message, state: FSMContext) -> None:
    await _text_step(
        message, state, "relevance", ProjectStates.goal, texts.PROJECT_STEPS[5]
    )


@router.message(ProjectStates.goal)
async def project_goal(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 2000)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(goal=value)
    await state.set_state(ProjectStates.format)
    formats = (
        "Мастер-класс",
        "Игра",
        "Квест",
        "Встреча",
        "Дебаты",
        "Волонтёрская акция",
        "Медиа-проект",
        "Экскурсия",
        "Форум",
        "Другое",
    )
    await message.answer(
        texts.PROJECT_STEPS[6],
        reply_markup=options_keyboard(
            [(label, f"project:format:{i}") for i, label in enumerate(formats)],
            columns=2,
        ),
    )


@router.callback_query(ProjectStates.format, F.data.startswith("project:format:"))
async def project_format(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    formats = (
        "Мастер-класс",
        "Игра",
        "Квест",
        "Встреча",
        "Дебаты",
        "Волонтёрская акция",
        "Медиа-проект",
        "Экскурсия",
        "Форум",
        "Другое",
    )
    try:
        value = formats[int(call.data.rsplit(":", 1)[-1])]
    except (ValueError, IndexError):
        return
    await state.update_data(format=value)
    await state.set_state(ProjectStates.program)
    await call.message.answer(texts.PROJECT_STEPS[7])


@router.message(ProjectStates.program)
async def project_program(message: Message, state: FSMContext) -> None:
    await _text_step(
        message, state, "program", ProjectStates.resources, texts.PROJECT_STEPS[8]
    )


@router.message(ProjectStates.resources)
async def project_resources(message: Message, state: FSMContext) -> None:
    await _text_step(
        message, state, "resources", ProjectStates.team, texts.PROJECT_STEPS[9]
    )


@router.message(ProjectStates.team)
async def project_team(message: Message, state: FSMContext) -> None:
    await _text_step(
        message, state, "team", ProjectStates.expected_result, texts.PROJECT_STEPS[10]
    )


@router.message(ProjectStates.expected_result)
async def project_result(message: Message, state: FSMContext) -> None:
    await _text_step(
        message,
        state,
        "expected_result",
        ProjectStates.needs_from_era,
        texts.PROJECT_STEPS[11],
    )


@router.message(ProjectStates.needs_from_era)
async def project_finish(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    ai_service: AIService,
) -> None:
    value = clean_text(message.text or "", 3000)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(needs_from_era=value)
    data = await state.get_data()
    await message.answer(texts.PROJECT_GENERATING)
    if data.get("use_ai"):
        try:
            document = await ai_service.generate_project(data)
        except AIUnavailableError:
            document = fallback_project_document(data)
    else:
        document = fallback_project_document(data)
    project = await create_project(
        session, author_id=user.id, data=data, document=document
    )
    await state.clear()
    await send_long_text(
        message, document, reply_markup=project_result_keyboard(project.id)
    )


@router.callback_query(F.data.startswith("project:save:"))
async def project_save(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(texts.PROJECT_SAVED)


@router.callback_query(F.data.startswith("project:improve:"))
async def project_improve_start(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    await call.answer()
    project = await session.get(Project, int(call.data.rsplit(":", 1)[-1]))
    if project is None or project.author_id != user.id:
        await call.message.answer(texts.NO_ACCESS)
        return
    await state.set_state(ProjectRevisionStates.instruction)
    await state.update_data(revision_project_id=project.id)
    await call.message.answer(
        "Напишите, что нужно усилить или изменить в проекте. Например: добавить интерактив, уточнить аудиторию или сделать результаты измеримыми."
    )


@router.message(ProjectRevisionStates.instruction)
async def project_improve_finish(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    ai_service: AIService,
) -> None:
    instruction = clean_text(message.text or "", 1500)
    if not instruction:
        await message.answer(texts.INVALID_INPUT)
        return
    project_id = int((await state.get_data())["revision_project_id"])
    project = await session.get(Project, project_id)
    if project is None or project.author_id != user.id:
        await state.clear()
        await message.answer(texts.NO_ACCESS)
        return
    try:
        improved = await ai_service.improve_project(
            project.generated_document or project.short_description, instruction
        )
    except AIUnavailableError:
        await state.clear()
        await message.answer(
            "ИИ сейчас недоступен. Черновик сохранён, и Вы сможете вернуться к доработке позже."
        )
        return
    project.generated_document = improved
    await audit(
        session,
        actor_id=user.id,
        action="project.improved_with_ai",
        entity_type="project",
        entity_id=project.id,
        new_value={"instruction": instruction},
    )
    await state.clear()
    await send_long_text(
        message, improved, reply_markup=project_result_keyboard(project.id)
    )


@router.callback_query(F.data.startswith("project:submit:"))
async def project_submit(
    call: CallbackQuery,
    session: AsyncSession,
    user: User,
    bot: Bot,
    settings: Settings,
) -> None:
    await call.answer()
    project = await session.get(Project, int(call.data.rsplit(":", 1)[-1]))
    if project is None or project.author_id != user.id:
        await call.message.answer(texts.NO_ACCESS)
        return
    project.status = ProjectStatus.PENDING_REVIEW
    await audit(
        session,
        actor_id=user.id,
        action="project.submitted",
        entity_type="project",
        entity_id=project.id,
    )
    await call.message.answer(texts.PROJECT_SUBMITTED)
    await notify_admins(
        bot, settings, f"Новый проект на рассмотрении: {project.title} (#{project.id})."
    )


@router.callback_query(F.data == "projects:drafts")
async def project_drafts(
    call: CallbackQuery, session: AsyncSession, user: User
) -> None:
    await call.answer()
    projects = (
        await session.scalars(
            select(Project)
            .where(Project.author_id == user.id, Project.status == ProjectStatus.DRAFT)
            .order_by(desc(Project.created_at))
        )
    ).all()
    body = "\n".join(f"• #{p.id} {p.title}" for p in projects) or "Черновиков пока нет."
    await call.message.answer(body)
